"""简历相关 Celery 任务。"""
from __future__ import annotations

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services.llm_service import LLMService
from app.services.resume_service import ResumeService
from app.services.retrieval_service import RetrievalService
from app.tasks.celery_app import celery_app, run_async

logger = get_logger(__name__)


@celery_app.task(name="resume.parse", bind=True, max_retries=2)
def parse_resume_task(self, resume_id: int) -> dict:
    """解析简历文本。"""
    async def _run() -> None:
        async with SessionLocal() as db:
            svc = ResumeService(db)
            await svc.parse_and_update(resume_id)

    try:
        run_async(_run())
        return {"resume_id": resume_id, "status": "ok"}
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=10) from exc


@celery_app.task(name="resume.index", bind=True, max_retries=2)
def index_resume_task(self, resume_id: int) -> dict:
    """简历建索引：embedding + 关键词 + 写 resume_vectors。"""

    async def _run() -> dict:
        async with SessionLocal() as db:
            resume_svc = ResumeService(db)
            resume = await resume_svc.get(resume_id)
            if not resume.resume_text:
                raise RuntimeError("简历尚未解析")

            llm = LLMService(db)
            embed_model = await llm.get_embedding_model()
            embedding = await embed_model.aembed_query(resume.resume_text)

            keywords = _extract_keywords(resume.resume_text, top_k=20)

            retr = RetrievalService(db)
            await retr.index_resume(
                resume_id=resume_id,
                text_content=resume.resume_text,
                embedding=embedding,
                keywords=keywords,
            )
            return {"resume_id": resume_id, "keywords": len(keywords)}

    try:
        result = run_async(_run())
        logger.info("resume.indexed", **result)
        return {"status": "ok", **result}
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=10) from exc


def _extract_keywords(text: str, top_k: int = 20) -> list[str]:
    """轻量关键词提取：jieba 切词 + 词频排序。

    设计文档 retrieval.md §5.2：jieba + TF-IDF。这里简化为词频（够 demo 用）。
    """
    try:
        import jieba
    except ImportError:
        # 没装 jieba 就返回空
        return []

    STOPWORDS = set("的 了 和 是 在 也 都 就 与 及 等 把 被 让 但 而 或 其 之")
    words = [w for w in jieba.lcut(text) if len(w) > 1 and w not in STOPWORDS]
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:top_k]]
