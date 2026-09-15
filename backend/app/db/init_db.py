"""启动初始化：自动建表 + 首次运行 seed 默认 mock provider。

本地零外部服务：不需要手动跑 alembic，app 启动时自动建表。

部署到免费平台时磁盘是临时的（每次重建/重启就清空），所以这里还负责
**从仓库内的脱敏种子库还原演示数据**：库文件不存在时直接复制一份，
比逐条 INSERT 快得多（13MB 的库秒级完成）。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.db import models  # noqa: F401  确保所有模型注册到 metadata
from app.db.base import Base
from app.db.models.llm_provider import LlmProvider
from app.db.session import SessionLocal, engine

logger = get_logger(__name__)

# backend/seed/demo_seed.db（由 scripts/export_demo_seed.py 生成，含脱敏样例数据）
SEED_DB_FILE = Path(__file__).resolve().parents[2] / "seed" / "demo_seed.db"


def _sqlite_file_from_url(url: str) -> Path | None:
    """从 DATABASE_URL 里取出 SQLite 文件路径；非 SQLite 返回 None。

    注意：URL 里的相对路径是相对**进程工作目录**解析的（与 engine 的行为一致）。
    """
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            return Path(url[len(prefix) :])
    return None


def _restore_seed_db_if_empty() -> None:
    """库文件不存在时，从仓库内的种子库复制一份（部署环境的数据还原）。"""
    db_file = _sqlite_file_from_url(settings.database_url)
    if db_file is None:
        return
    if db_file.exists() or not SEED_DB_FILE.exists():
        return
    db_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SEED_DB_FILE, db_file)
    logger.info(
        "db.restored_from_seed",
        db=str(db_file),
        seed=str(SEED_DB_FILE),
        size=db_file.stat().st_size,
    )


async def init_db() -> None:
    """还原种子库（如需）→ 建表（幂等）→ 无 provider 时写入默认 mock provider。"""
    # 0. 空库时从种子库还原演示数据（本地已有库则完全不动）
    _restore_seed_db_if_empty()

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
