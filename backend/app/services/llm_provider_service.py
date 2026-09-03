"""LLM Provider Service。

设计文档 §4：llm_providers 表 + 加密 API Key。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessException, ErrorCode
from app.core.logging import get_logger
from app.core.security import decrypt_api_key, encrypt_api_key
from app.db.models.llm_provider import LlmProvider

logger = get_logger(__name__)


def _mask(plain: str) -> str:
    """脱敏：首尾各 4 位。"""
    if not plain or len(plain) < 8:
        return "***"
    return plain[:4] + "***" + plain[-4:]


class LlmProviderService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(self) -> list[LlmProvider]:
        stmt = select(LlmProvider).order_by(LlmProvider.id.asc())
        return list((await self.db.execute(stmt)).scalars().all())

    async def get(self, provider_id: int) -> LlmProvider:
        p = (
            await self.db.execute(
                select(LlmProvider).where(LlmProvider.id == provider_id)
            )
        ).scalar_one_or_none()
        if p is None:
            raise BusinessException(
                ErrorCode.LLM_PROVIDER_NOT_FOUND, f"Provider {provider_id} 不存在"
            )
        return p

    async def create(
        self,
        name: str,
        provider_type: str,
        api_key: str | None = None,
        base_url: str | None = None,
        chat_model: str | None = None,
        embedding_model: str | None = None,
        is_default: bool = False,
        enabled: bool = True,
    ) -> LlmProvider:
        # 重名检查
        existing = (
            await self.db.execute(select(LlmProvider).where(LlmProvider.name == name))
        ).scalar_one_or_none()
        if existing is not None:
            raise BusinessException(
                ErrorCode.LLM_PROVIDER_NOT_FOUND, f"Provider 名 {name} 已存在"
            )

        p = LlmProvider(
            name=name,
            provider_type=provider_type,
            base_url=base_url,
            api_key_encrypted=encrypt_api_key(api_key or ""),
            chat_model=chat_model,
            embedding_model=embedding_model,
            is_default=is_default,
            enabled=enabled,
        )
        self.db.add(p)
        await self.db.flush()

        if is_default:
            await self._clear_other_defaults(p.id)

        await self.db.commit()
        await self.db.refresh(p)
        logger.info("llm_provider.created", id=p.id, name=p.name)
        return p

    async def update(
        self,
        provider_id: int,
        name: str | None = None,
        base_url: str | None = None,
        chat_model: str | None = None,
        embedding_model: str | None = None,
        api_key: str | None = None,
        is_default: bool | None = None,
        enabled: bool | None = None,
    ) -> LlmProvider:
        p = await self.get(provider_id)
        if name is not None:
            p.name = name
        if base_url is not None:
            p.base_url = base_url
        if chat_model is not None:
            p.chat_model = chat_model
        if embedding_model is not None:
            p.embedding_model = embedding_model
        if api_key:
            p.api_key_encrypted = encrypt_api_key(api_key)
        if enabled is not None:
            p.enabled = enabled
        if is_default is not None:
            p.is_default = is_default
            if is_default:
                await self._clear_other_defaults(p.id)

        await self.db.commit()
        await self.db.refresh(p)
        logger.info("llm_provider.updated", id=p.id)
        return p

    async def delete(self, provider_id: int) -> None:
        p = await self.get(provider_id)
        await self.db.delete(p)
        await self.db.commit()
        logger.info("llm_provider.deleted", id=provider_id)

    async def set_default(self, provider_id: int) -> LlmProvider:
        p = await self.get(provider_id)
        if not p.enabled:
            raise BusinessException(
                ErrorCode.LLM_PROVIDER_DISABLED, "禁用的 Provider 不能设为默认"
            )
        p.is_default = True
        await self._clear_other_defaults(p.id)
        await self.db.commit()
        await self.db.refresh(p)
        return p

    async def test_connection(self, provider_id: int) -> dict:
        """测试连接：调一次 chat 简单 prompt。"""
        from langchain_core.messages import HumanMessage

        p = await self.get(provider_id)
        if not p.enabled:
            raise BusinessException(
                ErrorCode.LLM_PROVIDER_DISABLED, "Provider 已禁用"
            )
        try:
            from app.services.llm_service import _build_chat_model

            chat = _build_chat_model(p)
            resp = await chat.ainvoke([HumanMessage(content="ping")])
            text = resp.content if hasattr(resp, "content") else str(resp)
            return {
                "ok": True,
                "provider": p.name,
                "message": str(text)[:200],
            }
        except BusinessException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm_provider.test_failed", id=provider_id, error=str(exc))
            return {
                "ok": False,
                "provider": p.name,
                "error": str(exc)[:500],
            }

    # ---------- 内部 ----------
    async def _clear_other_defaults(self, keep_id: int) -> None:
        """同一时刻只能有一个默认 Provider。"""
        others = (
            await self.db.execute(
                select(LlmProvider).where(
                    LlmProvider.is_default == True,  # noqa: E712
                    LlmProvider.id != keep_id,
                )
            )
        ).scalars().all()
        for o in others:
            o.is_default = False
        await self.db.flush()

    # ---------- 响应序列化 ----------
    @staticmethod
    def to_response(p: LlmProvider) -> dict:
        """生成对外响应（脱敏 API Key）。"""
        plain = ""
        if p.api_key_encrypted:
            try:
                plain = decrypt_api_key(p.api_key_encrypted)
            except Exception:  # noqa: BLE001
                plain = ""
        return {
            "id": p.id,
            "name": p.name,
            "provider_type": p.provider_type,
            "base_url": p.base_url,
            "chat_model": p.chat_model,
            "embedding_model": p.embedding_model,
            "is_default": p.is_default,
            "enabled": p.enabled,
            "has_api_key": bool(plain),
            "api_key_masked": _mask(plain) if plain else None,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }
