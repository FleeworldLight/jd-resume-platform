"""LLM 结构化输出 Schema（Pydantic BaseModel）。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class JdStructured(BaseModel):
    """JD 结构化抽取结果。"""

    company: Optional[str] = Field(default=None, description="公司名")
    position: Optional[str] = Field(default=None, description="岗位名")
    salary_min: Optional[int] = Field(default=None, description="薪资下限（千元/月）")
    salary_max: Optional[int] = Field(default=None, description="薪资上限（千元/月）")
    city: Optional[str] = Field(default=None, description="城市")
    experience: Optional[str] = Field(default=None, description="经验要求")
    education: Optional[str] = Field(default=None, description="学历要求")
    skills: list[str] = Field(default_factory=list, description="技能列表")
    responsibilities: list[str] = Field(default_factory=list, description="职责列表")
    requirements: list[str] = Field(default_factory=list, description="要求列表")
