"""LLM Service：统一 LLM 调用入口。

设计文档 §6.1：所有 LLM 调用走 LLMService.structured_invoke()。
LLM Provider 数据从 DB 读取（llm_providers 表）。
"""
from __future__ import annotations

from typing import Any, TypeVar, get_args, get_origin

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from pydantic_core import PydanticUndefined
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

    async def structured_invoke(
        self,
        prompt_template: ChatPromptTemplate,
        input_vars: dict[str, Any],
        output_schema: type[T],
        provider: LlmProvider | None = None,
    ) -> T:
        """调用 LLM 并返回结构化输出。

        - provider 为 mock 时：不调外部 API，直接按 schema 生成一份占位结果（离线可用）
        - 真实 provider：LangChain with_structured_output；失败抛 BusinessException
        """
        provider = provider or await self.get_default_provider()
        if provider.provider_type == "mock":
            logger.info("llm.mock_output", schema=output_schema.__name__)
            return _build_mock_output(output_schema)

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
                provider=provider.name,
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


# ---------- mock 结构化输出 ----------
def _mock_field_value(annotation: Any, field: Any) -> Any:
    """递归地为一个 Pydantic 字段生成合法占位值。"""
    # 字段自带默认值/工厂 → 直接用（保持结构完整、列表为空等）
    if field.default is not PydanticUndefined:
        return field.default
    if field.default_factory is not PydanticUndefined:
        return field.default_factory()

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is not None and type(None) in args:
        # Optional[X] → 给一个 X 的 mock（避免下游拿 None 炸）
        for a in args:
            if a is not type(None):
                return _mock_field_value(a, field)
        return None

    if origin is list:
        elem = args[0] if args else Any
        return [_mock_field_value(elem, field)]

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation(**_mock_kwargs(annotation))

    # 标量
    if annotation is str:
        return "（mock 占位）"
    if annotation is int:
        return 0
    if annotation is float:
        return 0.0
    if annotation is bool:
        return False
    return None


def _mock_kwargs(model: type[BaseModel]) -> dict[str, Any]:
    return {
        name: _mock_field_value(f.annotation, f)
        for name, f in model.model_fields.items()
    }


def _build_mock_output(output_schema: type[T]) -> T:
    """mock provider：返回一份能通过校验的占位结果（不调任何外部 API）。"""
    return output_schema(**_mock_kwargs(output_schema))
