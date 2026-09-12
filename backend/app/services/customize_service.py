"""定制简历 Service。"""
from __future__ import annotations

from app.core.exceptions import BusinessException, ErrorCode
from app.core.logging import get_logger
from app.db.models.jd import Jd
from app.db.models.resume import Resume
from app.prompts import CUSTOMIZE_PROMPT_V1
from app.schemas.customization import CustomizedResume, GapReport
from app.services.heuristic_pipeline import customize_resume
from app.services.llm_service import LLMService

logger = get_logger(__name__)


class CustomizeService:
    def __init__(self, llm_service: LLMService) -> None:
        self.llm = llm_service

    async def customize(
        self, jd: Jd, resume: Resume, gap: GapReport
    ) -> CustomizedResume:
        try:
            provider = await self.llm.get_default_provider()
            if getattr(provider, "provider_type", None) == "mock":
                # mock 下改走规则：只重排简历里已有的信息，不编造经历
                result = customize_resume(
                    jd.raw_text or "", jd.position, resume.resume_text or "", gap
                )
                result.extract_mode = "heuristic"
                return result

            result = await self.llm.structured_invoke(
                prompt_template=CUSTOMIZE_PROMPT_V1,
                input_vars={
                    "jd_text": jd.raw_text or "",
                    "resume_text": resume.resume_text or "",
                    "gap_report": gap.model_dump_json(),
                },
                output_schema=CustomizedResume,
            )
            result.extract_mode = "llm"
            return result
        except BusinessException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("customize.failed", error=str(exc))
            raise BusinessException(
                ErrorCode.LLM_INVOKE_FAILED, f"定制简历失败: {exc}"
            ) from exc
