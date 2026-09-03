"""定制化 Celery 任务。"""
from __future__ import annotations

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services.customization_service import CustomizationService
from app.services.llm_service import LLMService
from app.tasks.celery_app import celery_app, run_async

logger = get_logger(__name__)


@celery_app.task(name="customization.run", bind=True, max_retries=2)
def customize_resume_task(
    self, customization_id: int, question_count: int = 5
) -> dict:
    """定制化主任务：6 步流水线。"""

    async def _run() -> None:
        async with SessionLocal() as db:
            llm = LLMService(db)
            svc = CustomizationService(db, llm)
            await svc.execute(customization_id, question_count=question_count)

    try:
        run_async(_run())
        return {"customization_id": customization_id, "status": "ok"}
    except Exception as exc:  # noqa: BLE001
        if self.request.retries < self.max_retries:
            logger.warning(
                "customization.retry",
                id=customization_id,
                attempt=self.request.retries + 1,
                error=str(exc),
            )
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        logger.error(
            "customization.failed",
            id=customization_id,
            error=str(exc),
        )
        raise
