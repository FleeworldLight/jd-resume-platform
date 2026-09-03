"""定制化 Schemas（与 docs/modules/customization.md §4 对齐）。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------- 差距分析 ----------
Priority = Literal["HIGH", "MEDIUM", "LOW"]
Difficulty = Literal["EASY", "MEDIUM", "HARD"]


class MissingSkill(BaseModel):
    skill: str
    priority: Priority
    reason: str


class ExperienceGap(BaseModel):
    aspect: str
    current: str
    expected: str


class GapReport(BaseModel):
    match_score: int = Field(..., ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[MissingSkill] = Field(default_factory=list)
    experience_gaps: list[ExperienceGap] = Field(default_factory=list)
    recommended_focus: list[str] = Field(default_factory=list)


# ---------- 定制简历 ----------
class Experience(BaseModel):
    title: str
    company: str
    duration: str
    description: str
    achievements: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)


class Education(BaseModel):
    school: str
    major: str
    degree: str
    duration: str


class CustomizedResume(BaseModel):
    summary: str
    skills: list[str] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)


# ---------- 押题 ----------
class StarAnswer(BaseModel):
    situation: str
    task: str
    action: str
    result: str


class PredictedQuestion(BaseModel):
    category: str
    difficulty: Difficulty
    question: str
    star_answer: StarAnswer
    key_points: list[str] = Field(default_factory=list)
    hit_reason: str


class InterviewPrediction(BaseModel):
    questions: list[PredictedQuestion] = Field(default_factory=list)


# ---------- 评估 ----------
class RetrievalMetrics(BaseModel):
    recall_at_10: float
    precision_at_10: float
    ndcg_at_10: float
    vector_only: dict[str, Any] = Field(default_factory=dict)
    keyword_only: dict[str, Any] = Field(default_factory=dict)


# ---------- API 层 ----------
class CustomizationCreateRequest(BaseModel):
    jd_id: int = Field(..., ge=1)
    base_resume_id: int = Field(..., ge=1)
    question_count: int = Field(default=5, ge=1, le=20)


class CustomizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    jd_id: int
    base_resume_id: int
    status: str
    error_message: str | None = None
    retry_count: int
    provider_used: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CustomizationDetailResponse(CustomizationResponse):
    gap_report: dict[str, Any] | None = None
    customized_resume: dict[str, Any] | None = None
    prediction: dict[str, Any] | None = None
    retrieval_metrics: dict[str, Any] | None = None
    matched_resumes: list[Any] | None = None


class CustomizationList(BaseModel):
    items: list[CustomizationResponse]
    total: int
    page: int
    page_size: int


class CustomizationStatusResponse(BaseModel):
    id: int
    status: str
    error_message: str | None = None
    retry_count: int
    has_gap: bool = False
    has_resume: bool = False
    has_prediction: bool = False
