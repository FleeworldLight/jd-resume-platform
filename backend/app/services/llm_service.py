"""LLM Service：统一 LLM 调用入口。

设计文档 §6.1：所有 LLM 调用走 LLMService.structured_invoke()。
LLM Provider 数据从 DB 读取（llm_providers 表）。
"""
from __future__ import annotations

from typing import Any, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import BusinessException, ErrorCode
from app.core.logging import get_logger
from app.core.security import decrypt_api_key
from app.db.models.llm_provider import LlmProvider

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMService:
    """统一 LLM 调用入口。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_embedding_model(
        self, provider: LlmProvider | None = None
    ):
        """按 provider 构造 Embeddings 实例。"""
        provider = provider or await self.get_default_provider()
        return _build_embedding_model(provider)

    async def get_default_provider(self) -> LlmProvider:
        """取默认（且启用）的 provider。"""
        stmt = (
            select(LlmProvider)
            .where(LlmProvider.enabled == True)  # noqa: E712
            .where(LlmProvider.is_default == True)  # noqa: E712
            .limit(1)
        )
        result = await self.db.execute(stmt)
        provider = result.scalar_one_or_none()
        if provider is None:
            raise BusinessException(
                ErrorCode.LLM_NO_PROVIDER_AVAILABLE,
                "未配置默认 LLM Provider，请先在模型管理页面添加",
            )
        return provider

    async def get_chat_model(
        self, provider: LlmProvider | None = None
    ) -> BaseChatModel:
        """根据 provider 构造 LangChain ChatModel。"""
        provider = provider or await self.get_default_provider()
        return _build_chat_model(provider)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def structured_invoke(
        self,
        prompt_template: ChatPromptTemplate,
        input_vars: dict[str, Any],
        output_schema: type[T],
        provider: LlmProvider | None = None,
    ) -> T:
        """调用 LLM 并返回结构化输出。

        失败由 tenacity 自动重试 3 次；最终失败抛 BusinessException。
        """
        chat = await self.get_chat_model(provider)
        try:
            structured = chat.with_structured_output(output_schema)
            chain = prompt_template | structured
            result = await chain.ainvoke(input_vars)
        except BusinessException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "llm.invoke_failed",
                error=str(exc),
                provider=provider.name if provider else "default",
            )
            raise BusinessException(
                ErrorCode.LLM_INVOKE_FAILED, f"LLM 调用失败: {exc}"
            ) from exc

        if not isinstance(result, output_schema):
            raise BusinessException(
                ErrorCode.LLM_STRUCTURED_OUTPUT_FAILED,
                f"LLM 输出类型不符: {type(result).__name__}",
            )
        return result


def _build_chat_model(provider: LlmProvider) -> BaseChatModel:
    """按 provider_type 构造具体的 ChatModel。"""
    api_key = decrypt_api_key(provider.api_key_encrypted or "")
    if provider.provider_type == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=provider.chat_model or "gpt-4o-mini",
            api_key=api_key or None,
            base_url=provider.base_url or None,
            temperature=0.2,
        )
    if provider.provider_type == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=provider.chat_model or "claude-3-5-sonnet-latest",
            api_key=api_key or None,
            base_url=provider.base_url or None,
            temperature=0.2,
        )
    if provider.provider_type == "mock":
        # 内部测试用：返回固定字段，type 不真校验
        from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

        return GenericFakeChatModel(messages=iter(["ok"]))

    raise BusinessException(
        ErrorCode.LLM_PROVIDER_TYPE_UNKNOWN,
        f"不支持的 provider_type: {provider.provider_type}",
    )


def _build_embedding_model(provider: LlmProvider):
    """按 provider_type 构造 Embeddings。"""
    api_key = decrypt_api_key(provider.api_key_encrypted or "")
    if provider.provider_type == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=provider.embedding_model or "text-embedding-3-small",
            api_key=api_key or None,
            base_url=provider.base_url or None,
        )
    if provider.provider_type == "mock":
        # 测试用：返回稳定的伪向量（按文本 hash 派生）
        from app.services._fake_embeddings import FakeEmbeddings

        return FakeEmbeddings(dim=settings.embedding_dim)
    raise BusinessException(
        ErrorCode.LLM_PROVIDER_TYPE_UNKNOWN,
        f"Embedding 不支持 provider_type: {provider.provider_type}",
    )
