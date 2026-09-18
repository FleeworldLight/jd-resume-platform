"""定制化 Schemas（与 docs/modules/customization.md §4 对齐）。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.resume_content import ResumeContent


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
    # 生成方式：llm（真实模型）/ heuristic（本地规则兜底，mock 下使用）
    extract_mode: str | None = None


# ---------- 定制简历（旧结构，保留向后兼容） ----------
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
    extract_mode: str | None = None


# ---------- 定制简历（新结构：成品就是「一份简历」） ----------
class SkillGroup(BaseModel):
    """技能分组（按类别归拢，组内按与 JD 的相关度排序）。"""

    category: str
    items: list[str] = Field(default_factory=list)


class Suggestion(BaseModel):
    """待用户逐条确认的候选表述。

    「补足简历不足」的唯一入口：JD 要求、而简历完全没有的内容，
    只以候选句形式提出，**绝不自动写进简历正文**。
    ``confirmed=False`` 时，导出会在对应位置标注「未证实 · 待确认」。
    """

    id: str
    target: str = "summary"      # 位置锚点：summary / skills / experiences:1 / projects:0
    target_label: str = ""       # 人类可读位置，如「个人项目 · 电商秒杀系统」
    skill: str = ""
    text: str = ""               # 候选句（需用户改成自己真实的做法）
    reason: str = ""             # 依据：引用 JD 原文
    priority: Priority = "MEDIUM"
    confirmed: bool = False


class RankingEntry(BaseModel):
    """单条经历/项目的岗位相关度，用来解释「为什么这条排在前面」。"""

    section: Literal["experiences", "projects"]
    index: int
    title: str = ""
    score: int = 0
    matched_skills: list[str] = Field(default_factory=list)


class TailoredResume(BaseModel):
    """定制后的完整简历本体（可直接投递）+ 定制元信息。"""

    content: ResumeContent = Field(default_factory=ResumeContent)
    target_position: str = ""
    skill_groups: list[SkillGroup] = Field(default_factory=list)
    tailor_notes: list[str] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)
    ranking: list[RankingEntry] = Field(default_factory=list)
    extract_mode: str | None = None


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
    extract_mode: str | None = None


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


class SuggestionUpdateRequest(BaseModel):
    """逐条确认/驳回候选句。``confirmed`` 为 False 表示驳回（保留但不进正文）。"""

    confirmed: bool = True


class SuggestionApplyRequest(BaseModel):
    """批量确认：不传 ids 表示「全部确认」。"""

    ids: list[str] | None = None
    confirmed: bool = True


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
    # 简历正文的纯文本预览（供前端/调试直接看「成品长什么样」）
    resume_text: str | None = None


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
    suggestion_total: int = 0
    suggestion_confirmed: int = 0
