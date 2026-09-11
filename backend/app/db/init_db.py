"""启动初始化：自动建表 + 首次运行 seed 默认 mock provider。

本地零外部服务：不需要手动跑 alembic，app 启动时自动建表。
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.logging import get_logger
from app.db import models  # noqa: F401  确保所有模型注册到 metadata
from app.db.base import Base
from app.db.models.llm_provider import LlmProvider
from app.db.session import SessionLocal, engine

logger = get_logger(__name__)


async def init_db() -> None:
    """建表（幂等）；无任何 provider 时写入一个默认 mock provider。"""
    # 1. 建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. seed：没有任何 provider 时插入 mock，保证离线可用（embedding/结构化都有 mock 实现）
    async with SessionLocal() as db:
        existing = (
            await db.execute(select(LlmProvider.id).limit(1))
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                LlmProvider(
                    name="mock",
                    provider_type="mock",
                    is_default=True,
                    enabled=True,
                )
            )
            await db.commit()
            logger.info("db.seeded_mock_provider")
