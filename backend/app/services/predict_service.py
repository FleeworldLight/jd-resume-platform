"""押题 Service。"""
from __future__ import annotations

from app.core.exceptions import BusinessException, ErrorCode
from app.core.logging import get_logger
from app.db.models.jd import Jd
from app.prompts import PREDICT_PROMPT_V1
from app.schemas.customization import CustomizedResume, InterviewPrediction
from app.services.llm_service import LLMService

logger = get_logger(__name__)


class PredictService:
    def __init__(self, llm_service: LLMService) -> None:
        self.llm = llm_service

    async def predict(
        self,
        jd: Jd,
        customized_resume: CustomizedResume,
        question_count: int = 5,
    ) -> InterviewPrediction:
        try:
            return await self.llm.structured_invoke(
                prompt_template=PREDICT_PROMPT_V1,
                input_vars={
                    "jd_text": jd.raw_text or "",
                    "customized_resume": customized_resume.model_dump_json(),
                    "question_count": question_count,
                },
                output_schema=InterviewPrediction,
            )
        except BusinessException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("predict.failed", error=str(exc))
            raise BusinessException(
                ErrorCode.LLM_INVOKE_FAILED, f"押题失败: {exc}"
            ) from exc
