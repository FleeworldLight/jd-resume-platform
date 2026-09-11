"""简历向量表。

SQLite 本地版：embedding 用 LargeBinary 存 numpy float32 字节流，
Python 端算 cosine；关键词存 JSON，Python 端算 Jaccard。无需任何 PG 扩展。
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, JSON, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ResumeVector(Base, TimestampMixin):
    __tablename__ = "resume_vectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resumes.id"), nullable=False, unique=True
    )

    # 向量（numpy float32 字节流）
    embedding = mapped_column(LargeBinary, nullable=True)

    # 关键词（纯 Python Jaccard 用）
    keywords: Mapped[list | None] = mapped_column(JSON, nullable=True)
