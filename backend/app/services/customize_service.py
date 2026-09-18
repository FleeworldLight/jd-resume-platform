"""定制简历 Service。

产物形态：一份**完整简历**（:class:`TailoredResume`），而不是分析报告。
``TailoredResume.content`` 是可直接投递的简历本体，
`skill_groups` 按类别分组、组内按岗位相关度排序，
`suggestions` 存放「岗位要求但简历没有依据」的候选句（默认未确认）。
"""
from __future__ import annotations

from app.core.exceptions import BusinessException, ErrorCode
from app.core.logging import get_logger
from app.db.models.jd import Jd
from app.db.models.resume import Resume
from app.prompts import CUSTOMIZE_PROMPT_V1
from app.schemas.customization import GapReport, TailoredResume
from app.services.llm_service import LLMService
from app.services.tailor_pipeline import build_tailored_resume

logger = get_logger(__name__)


class CustomizeService:
    def __init__(self, llm_service: LLMService) -> None:
        self.llm = llm_service

    async def customize(
        self, jd: Jd, resume: Resume, gap: GapReport
    ) -> TailoredResume:
        try:
            provider = await self.llm.get_default_provider()
            if getattr(provider, "provider_type", None) == "mock":
                # mock 下走规则：只重排 / 归位简历里已有的事实，不新增任何经历
                result = build_tailored_resume(
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
                output_schema=TailoredResume,
            )
            # 诚实兜底：无论模型怎么答，候选句一律先置为「未确认」，
            # 必须由用户在前端逐条确认后才进简历正文。
            for s in result.suggestions:
                s.confirmed = False
            result.extract_mode = "llm"
            return result
        except BusinessException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("customize.failed", error=str(exc))
            raise BusinessException(
                ErrorCode.LLM_INVOKE_FAILED, f"定制简历失败: {exc}"
            ) from exc
