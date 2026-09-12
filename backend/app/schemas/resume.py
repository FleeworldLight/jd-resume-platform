"""简历 Schemas。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResumeResponse(BaseModel):
    """简历响应（不含全文）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    content_hash: str
    parse_status: str
    parse_error: str | None = None
    created_at: datetime
    updated_at: datetime


class ResumeDetailResponse(ResumeResponse):
    """简历详情（含文本）。"""

    resume_text: str | None = None
    storage_path: str | None = None


class ResumeList(BaseModel):
    items: list[ResumeResponse]
    total: int
    page: int
    page_size: int


class ResumeStatusResponse(BaseModel):
    id: int
    parse_status: str
    parse_error: str | None = None


class ResumeUpdateRequest(BaseModel):
    """在线编辑保存：提交编辑后的简历全文。"""

    resume_text: str = Field(min_length=1, description="编辑后的简历全文（纯文本）")
