"""JD Schemas。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JdTextRequest(BaseModel):
    """粘贴 JD 文本。"""

    text: str = Field(..., min_length=10, max_length=20_000)


class JdUrlRequest(BaseModel):
    """提交 JD URL（牛客/Boss）。"""

    url: str = Field(..., min_length=10, max_length=512)

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL 必须以 http:// 或 https:// 开头")
        return v


class JdResponse(BaseModel):
    """JD 响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    source_url: str | None = None
    raw_text: str | None = None
    company: str | None = None
    position: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    city: str | None = None
    experience: str | None = None
    education: str | None = None
    skills: list[str] | None = None
    responsibilities: list[str] | None = None
    requirements: list[str] | None = None
    structured: dict[str, Any] | None = None
    crawl_status: str
    crawl_error: str | None = None
    created_at: datetime
    updated_at: datetime


class JdList(BaseModel):
    items: list[JdResponse]
    total: int
    page: int
    page_size: int


class JdStatusResponse(BaseModel):
    id: int
    crawl_status: str
    crawl_error: str | None = None
    has_structured: bool = False
