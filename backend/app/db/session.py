"""异步会话工厂（SQLite + aiosqlite）。

本地零外部服务：默认 sqlite+aiosqlite，双击 start.bat 即可启动。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# 确保数据目录存在（SQLite 文件 + 简历存储）
if settings.database_url.startswith("sqlite"):
    _db_path = settings.database_url.split("///", 1)[-1]
    if _db_path and _db_path != ":memory:":
        Path(_db_path).parent.mkdir(parents=True, exist_ok=True)
settings.resume_storage_dir.mkdir(parents=True, exist_ok=True)

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
)

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：每个请求一个 session。"""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db() -> None:
    await engine.dispose()
