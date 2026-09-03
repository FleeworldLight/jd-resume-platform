"""JD Service：粘贴/抓取/结构化抽取。

设计文档 §8 + docs/modules/jd.md。
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessException, ErrorCode
from app.core.logging import get_logger
from app.crawler.factory import detect_source, get_crawler
from app.db.models.jd import Jd
from app.prompts import JD_EXTRACT_PROMPT_V1
from app.schemas.llm_output import JdStructured
from app.services.llm_service import LLMService

logger = get_logger(__name__)


class JdService:
    def __init__(self, db: AsyncSession, llm_service: LLMService) -> None:
        self.db = db
        self.llm = llm_service

    # ---------- 创建 ----------
    async def create_from_text(self, text: str) -> Jd:
        """粘贴文本：同步结构化。"""
        jd = Jd(
            source="MANUAL",
            raw_text=text,
            crawl_status="PENDING",
        )
        self.db.add(jd)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(jd)

        # 同步结构化（失败不回滚，留痕）
        try:
            await self.structure_jd(jd.id)
        except BusinessException as exc:
            logger.warning(
                "jd.structure_failed",
                jd_id=jd.id,
                code=int(exc.code),
                error=exc.message,
            )
            # 重新读一次
            jd = await self.get(jd.id)
        return jd

    async def create_from_url(self, url: str) -> Jd:
        """提交 URL：先建记录（PENDING），由 Celery 异步抓取 + 结构化。"""
        source = detect_source(url)
        jd = Jd(
            source=source,
            source_url=url,
            raw_text="",
            crawl_status="PENDING",
        )
        self.db.add(jd)
        await self.db.commit()
        await self.db.refresh(jd)
        logger.info("jd.url_submitted", jd_id=jd.id, source=source)
        return jd

    # ---------- 查询 ----------
    async def get(self, jd_id: int) -> Jd:
        stmt = select(Jd).where(Jd.id == jd_id)
        jd = (await self.db.execute(stmt)).scalar_one_or_none()
        if jd is None:
            raise BusinessException(ErrorCode.JD_NOT_FOUND, f"JD {jd_id} 不存在")
        return jd

    async def list(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[Jd], int]:
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size

        total = (await self.db.execute(select(func.count(Jd.id)))).scalar_one()
        stmt = (
            select(Jd)
            .order_by(Jd.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        items = list((await self.db.execute(stmt)).scalars().all())
        return items, int(total)

    # ---------- 删除 ----------
    async def delete(self, jd_id: int) -> None:
        jd = await self.get(jd_id)
        await self.db.delete(jd)
        await self.db.commit()
        logger.info("jd.deleted", jd_id=jd_id)

    # ---------- 抓取（由 Celery 任务调用） ----------
    async def crawl_and_update(self, jd_id: int) -> None:
        """抓取 URL 原文 + 落库 + 触发结构化。"""
        jd = await self.get(jd_id)
        if jd.crawl_status == "COMPLETED":
            return
        if not jd.source_url:
            raise BusinessException(ErrorCode.JD_NOT_FOUND, "URL 缺失")

        jd.crawl_status = "PROCESSING"
        await self.db.commit()

        try:
            strategy = get_crawler(jd.source)
            raw_text = await strategy.crawl(jd.source_url)
            if not raw_text or len(raw_text) < 50:
                raise BusinessException(
                    ErrorCode.JD_CRAWL_FAILED, "抓取内容为空或过短"
                )
            jd.raw_text = raw_text
            jd.crawl_status = "PARSED"
            await self.db.commit()
            logger.info("jd.crawled", jd_id=jd_id, length=len(raw_text))

            # 继续结构化
            await self.structure_jd(jd_id)
        except BusinessException as exc:
            jd.crawl_status = "FAILED"
            jd.crawl_error = exc.message[:500]
            await self.db.commit()
            raise
        except Exception as exc:  # noqa: BLE001
            jd.crawl_status = "FAILED"
            jd.crawl_error = str(exc)[:500]
            await self.db.commit()
            raise BusinessException(
                ErrorCode.JD_CRAWL_FAILED, f"抓取异常: {exc}"
            ) from exc

    # ---------- 结构化（LLM） ----------
    async def structure_jd(self, jd_id: int) -> None:
        """对 raw_text 做结构化抽取。"""
        jd = await self.get(jd_id)
        if not jd.raw_text:
            raise BusinessException(ErrorCode.INVALID_PARAMS, "JD 原文为空")

        try:
            structured = await self.llm.structured_invoke(
                prompt_template=JD_EXTRACT_PROMPT_V1,
                input_vars={"jd_text": jd.raw_text},
                output_schema=JdStructured,
            )
        except BusinessException as exc:
            jd.crawl_status = "FAILED"
            jd.crawl_error = exc.message[:500]
            await self.db.commit()
            raise

        self._apply_structured(jd, structured)
        jd.crawl_status = "COMPLETED"
        jd.crawl_error = None
        await self.db.commit()
        logger.info("jd.structured", jd_id=jd_id)

    def _apply_structured(self, jd: Jd, s: JdStructured) -> None:
        jd.company = s.company
        jd.position = s.position
        jd.salary_min = s.salary_min
        jd.salary_max = s.salary_max
        jd.city = s.city
        jd.experience = s.experience
        jd.education = s.education
        jd.skills = s.skills
        jd.responsibilities = s.responsibilities
        jd.requirements = s.requirements
        jd.structured = s.model_dump()
