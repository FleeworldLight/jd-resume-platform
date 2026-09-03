"""FastAPI 依赖注入。"""
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.services.llm_service import LLMService


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def get_llm_service(
    db: AsyncSession = Depends(get_db),
) -> LLMService:
    return LLMService(db)
