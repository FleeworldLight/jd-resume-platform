"""SQLAlchemy ORM 模型（与 design.md §4 数据模型对应）。"""
from app.db.models.resume import Resume
from app.db.models.jd import Jd
from app.db.models.customization import Customization
from app.db.models.resume_vector import ResumeVector
from app.db.models.evaluation_log import EvaluationLog
from app.db.models.llm_provider import LlmProvider

__all__ = [
    "Resume",
    "Jd",
    "Customization",
    "ResumeVector",
    "EvaluationLog",
    "LlmProvider",
]
