"""JD 相关 Celery 任务。"""
from __future__ import annotations

from app.db.session import SessionLocal
from app.services.jd_service import JdService
from app.services.llm_service import LLMService
from app.tasks.celery_app import celery_app, run_async


@celery_app.task(name="jd.crawl", bind=True, max_retries=2)
def crawl_jd_task(self, jd_id: int) -> dict:
    """抓取 JD 原文 + 结构化。"""

    async def _run() -> None:
        async with SessionLocal() as db:
            llm = LLMService(db)
            svc = JdService(db, llm)
            await svc.crawl_and_update(jd_id)

    try:
        run_async(_run())
        return {"jd_id": jd_id, "status": "ok"}
    except Exception as exc:  # noqa: BLE001
        # 抓取失败可重试（1分钟后）
        raise self.retry(exc=exc, countdown=60) from exc


@celery_app.task(name="jd.structure", bind=True, max_retries=2)
def structure_jd_task(self, jd_id: int) -> dict:
    """仅做结构化（当 crawl 已成功 raw_text 已落库）。"""

    async def _run() -> None:
        async with SessionLocal() as db:
            llm = LLMService(db)
            svc = JdService(db, llm)
            await svc.structure_jd(jd_id)

    try:
        run_async(_run())
        return {"jd_id": jd_id, "status": "ok"}
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=30) from exc
