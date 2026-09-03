"""JD 模型。"""
from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Jd(Base, TimestampMixin):
    __tablename__ = "jds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    company: Mapped[str | None] = mapped_column(String(128), nullable=True)
    position: Mapped[str | None] = mapped_column(String(128), nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    experience: Mapped[str | None] = mapped_column(String(64), nullable=True)
    education: Mapped[str | None] = mapped_column(String(64), nullable=True)

    skills: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    responsibilities: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    requirements: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    structured: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    crawl_status: Mapped[str] = mapped_column(
        String(32), default="PENDING", nullable=False
    )
    crawl_error: Mapped[str | None] = mapped_column(Text, nullable=True)
