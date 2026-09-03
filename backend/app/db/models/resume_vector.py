"""简历向量表（pgvector + tsvector 混合召回）。"""
from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.core.config import settings
from app.db.base import Base, TimestampMixin


class ResumeVector(Base, TimestampMixin):
    __tablename__ = "resume_vectors"
    __table_args__ = (
        UniqueConstraint("resume_id", name="uq_resume_vectors_resume_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("resumes.id"), nullable=False
    )

    # vector(1024) 与 design.md §4 一致，维度由 settings.embedding_dim 控制
    embedding = mapped_column(Vector(settings.embedding_dim), nullable=True)

    # PostgreSQL 全文检索
    search_tsv: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    keywords: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
