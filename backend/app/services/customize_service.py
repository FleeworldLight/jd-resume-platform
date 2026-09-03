"""定制简历 Service。"""
from __future__ import annotations

from app.core.exceptions import BusinessException, ErrorCode
from app.core.logging import get_logger
from app.db.models.jd import Jd
from app.db.models.resume import Resume
from app.prompts import CUSTOMIZE_PROMPT_V1
from app.schemas.customization import CustomizedResume, GapReport
from app.services.llm_service import LLMService

logger = get_logger(__name__)


class CustomizeService:
    def __init__(self, llm_service: LLMService) -> None:
        self.llm = llm_service

    async def customize(
        self, jd: Jd, resume: Resume, gap: GapReport
    ) -> CustomizedResume:
        try:
            return await self.llm.structured_invoke(
                prompt_template=CUSTOMIZE_PROMPT_V1,
                input_vars={
                    "jd_text": jd.raw_text or "",
                    "resume_text": resume.resume_text or "",
                    "gap_report": gap.model_dump_json(),
                },
                output_schema=CustomizedResume,
            )
        except BusinessException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("customize.failed", error=str(exc))
            raise BusinessException(
                ErrorCode.LLM_INVOKE_FAILED, f"定制简历失败: {exc}"
            ) from exc
