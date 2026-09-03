"""差距分析 Service。"""
from __future__ import annotations

import json

from app.core.exceptions import BusinessException, ErrorCode
from app.core.logging import get_logger
from app.db.models.jd import Jd
from app.db.models.resume import Resume
from app.prompts import GAP_ANALYSIS_PROMPT_V1
from app.schemas.customization import GapReport
from app.services.llm_service import LLMService

logger = get_logger(__name__)


class GapAnalysisService:
    def __init__(self, llm_service: LLMService) -> None:
        self.llm = llm_service

    async def analyze(self, jd: Jd, resume: Resume) -> GapReport:
        if not jd.raw_text:
            raise BusinessException(ErrorCode.JD_NOT_FOUND, "JD 原文为空")
        if not resume.resume_text:
            raise BusinessException(ErrorCode.RESUME_NOT_FOUND, "简历文本为空")
        try:
            return await self.llm.structured_invoke(
                prompt_template=GAP_ANALYSIS_PROMPT_V1,
                input_vars={
                    "jd_text": jd.raw_text,
                    "jd_structured": json.dumps(jd.structured or {}, ensure_ascii=False),
                    "resume_text": resume.resume_text,
                },
                output_schema=GapReport,
            )
        except BusinessException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("gap_analysis.failed", error=str(exc))
            raise BusinessException(
                ErrorCode.LLM_INVOKE_FAILED, f"差距分析失败: {exc}"
            ) from exc
