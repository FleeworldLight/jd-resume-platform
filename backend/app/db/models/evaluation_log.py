"""评估日志。"""
from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EvaluationLog(Base, TimestampMixin):
    __tablename__ = "evaluation_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customization_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
