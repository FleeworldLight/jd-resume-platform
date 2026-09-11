"""定制化任务模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Customization(Base, TimestampMixin):
    __tablename__ = "customizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    jd_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("jds.id"), nullable=False
    )
    base_resume_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resumes.id"), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(32), default="PENDING", nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    gap_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    customized_resume: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prediction: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retrieval_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    matched_resumes: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    provider_used: Mapped[str | None] = mapped_column(String(64), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
