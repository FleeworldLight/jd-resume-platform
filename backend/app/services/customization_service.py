"""定制化主服务：召回 + 评估 + 差距 + 定制 + 押题 + 落库。

设计文档 §6.3 + docs/modules/customization.md §5.1。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessException, ErrorCode
from app.core.logging import get_logger
from app.db.models.customization import Customization
from app.db.models.jd import Jd
from app.db.models.resume import Resume
from app.services.customize_service import CustomizeService
from app.services.evaluation_service import EvaluationService
from app.services.gap_analysis_service import GapAnalysisService
from app.services.llm_service import LLMService
from app.services.predict_service import PredictService
from app.services.retrieval_service import RetrievalService

logger = get_logger(__name__)


class CustomizationService:
    def __init__(
        self,
        db: AsyncSession,
        llm_service: LLMService,
    ) -> None:
        self.db = db
        self.llm = llm_service
        self.retrieval = RetrievalService(db)
        self.evaluation = EvaluationService()
        self.gap = GapAnalysisService(llm_service)
        self.customize = CustomizeService(llm_service)
        self.predict = PredictService(llm_service)

    # ---------- 创建任务 ----------
    async def create(
        self, jd_id: int, base_resume_id: int, question_count: int = 5
    ) -> Customization:
        jd = await self._get_jd(jd_id)
        resume = await self._get_resume(base_resume_id)

        # PARSED：抓取阶段已把字段抽好（raw_text + 公司/岗位/城市/薪资…），
        # COMPLETED：又跑过一遍结构化。两者都足以支撑差距分析，
        # 只把 PENDING / PROCESSING / FAILED 拦掉。
        if jd.crawl_status not in ("COMPLETED", "PARSED"):
            raise BusinessException(
                ErrorCode.CUSTOMIZATION_INVALID_INPUT,
                f"JD 状态为 {jd.crawl_status}，尚未抓取完成，请先抓取或重新解析",
            )
        if not (jd.raw_text or "").strip():
            raise BusinessException(
                ErrorCode.CUSTOMIZATION_INVALID_INPUT, "JD 原文为空，无法分析"
            )
        if resume.parse_status != "COMPLETED":
            raise BusinessException(
                ErrorCode.CUSTOMIZATION_INVALID_INPUT,
                f"简历状态为 {resume.parse_status}，未完成解析",
            )

        c = Customization(
            jd_id=jd_id,
            base_resume_id=base_resume_id,
            status="PENDING",
        )
        self.db.add(c)
        await self.db.commit()
        await self.db.refresh(c)
        logger.info("customization.created", id=c.id, jd_id=jd_id, resume_id=base_resume_id)
        return c

    # ---------- 乐观锁抢任务 ----------
    async def claim(self, customization_id: int) -> bool:
        """PENDING → PROCESSING，成功返回 True（被其他 worker 抢走返回 False）。"""
        from sqlalchemy import update

        result = await self.db.execute(
            update(Customization)
            .where(Customization.id == customization_id)
            .where(Customization.status == "PENDING")
            .values(status="PROCESSING", started_at=datetime.utcnow())
        )
        await self.db.commit()
        return result.rowcount > 0

    # ---------- 主执行 ----------
    async def execute(
        self, customization_id: int, question_count: int = 5
    ) -> None:
        c = await self._get_customization(customization_id)
        if c.status == "COMPLETED":
            return
        if not await self.claim(customization_id):
            logger.info("customization.already_claimed", id=customization_id)
            return

        c = await self._get_customization(customization_id)
        jd = await self._get_jd(c.jd_id)
        resume = await self._get_resume(c.base_resume_id)

        try:
            # Step 1: 召回（用 query embedding）
            embed_model = await self.llm.get_embedding_model()
            query_emb = await embed_model.aembed_query(jd.raw_text or "")

            # 三种策略都跑，便于对比
            vec_results = await self.retrieval.vector_search(
                jd.raw_text, top_k=10, query_embedding=query_emb
            )
            kw_results = await self.retrieval.keyword_search(jd.raw_text, top_k=10)
            hybrid = await self.retrieval.hybrid_search(
                jd.raw_text,
                top_k=10,
                query_embedding=query_emb,
                strategy="HYBRID",
            )

            # Step 2: 评估（ground_truth = 当前用户的简历）
            ground_truth = {c.base_resume_id}
            vec_metrics = self.evaluation.evaluate(vec_results, ground_truth, k=10)
            kw_metrics = self.evaluation.evaluate(kw_results, ground_truth, k=10)
            hybrid_metrics = self.evaluation.evaluate(
                hybrid.results, ground_truth, k=10
            )
            retrieval_metrics = {
                "hybrid": hybrid_metrics.to_dict(),
                "vector_only": vec_metrics.to_dict(),
                "keyword_only": kw_metrics.to_dict(),
            }

            # Step 3: 差距分析
            gap_report = await self.gap.analyze(jd, resume)

            # Step 4: 定制简历
            customized = await self.customize.customize(jd, resume, gap_report)

            # Step 5: 押题
            prediction = await self.predict.predict(
                jd, customized, question_count=question_count, gap=gap_report
            )

            # Step 6: 落库
            c.gap_report = gap_report.model_dump()
            c.customized_resume = customized.model_dump()
            c.prediction = prediction.model_dump()
            c.retrieval_metrics = retrieval_metrics
            c.matched_resumes = [r.to_dict() for r in hybrid.results]
            c.status = "COMPLETED"
            c.completed_at = datetime.utcnow()
            # 取默认 provider 名（mock 下实际走的是本地规则，标注清楚免得误解）
            try:
                provider = await self.llm.get_default_provider()
                mode = (gap_report.extract_mode or "").strip()
                c.provider_used = (
                    f"{provider.name}（本地规则）" if mode == "heuristic" else provider.name
                )
            except BusinessException:
                c.provider_used = None
            await self.db.commit()
            logger.info("customization.completed", id=customization_id)
        except BusinessException as exc:
            c.status = "FAILED"
            c.error_message = exc.message[:500]
            c.completed_at = datetime.utcnow()
            c.retry_count += 1
            await self.db.commit()
            raise
        except Exception as exc:  # noqa: BLE001
            c.status = "FAILED"
            c.error_message = str(exc)[:500]
            c.completed_at = datetime.utcnow()
            c.retry_count += 1
            await self.db.commit()
            raise BusinessException(
                ErrorCode.CUSTOMIZATION_FAILED, f"定制化失败: {exc}"
            ) from exc

    # ---------- 查询 ----------
    async def get(self, customization_id: int) -> Customization:
        return await self._get_customization(customization_id)

    async def list(
        self, page: int = 1, page_size: int = 20, status: str | None = None
    ) -> tuple[list[Customization], int]:
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size

        stmt_count = select(func.count(Customization.id))
        stmt = (
            select(Customization)
            .order_by(Customization.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        if status:
            stmt_count = stmt_count.where(Customization.status == status)
            stmt = stmt.where(Customization.status == status)

        total = (await self.db.execute(stmt_count)).scalar_one()
        items = list((await self.db.execute(stmt)).scalars().all())
        return items, int(total)

    async def delete(self, customization_id: int) -> None:
        c = await self._get_customization(customization_id)
        await self.db.delete(c)
        await self.db.commit()

    async def retry(self, customization_id: int) -> None:
        c = await self._get_customization(customization_id)
        if c.status not in ("FAILED", "PENDING"):
            raise BusinessException(
                ErrorCode.CUSTOMIZATION_PROCESSING,
                f"当前状态 {c.status} 不能重试",
            )
        c.status = "PENDING"
        c.error_message = None
        await self.db.commit()

    # ---------- 内部 helpers ----------
    async def _get_jd(self, jd_id: int) -> Jd:
        jd = (await self.db.execute(select(Jd).where(Jd.id == jd_id))).scalar_one_or_none()
        if jd is None:
            raise BusinessException(ErrorCode.JD_NOT_FOUND, f"JD {jd_id} 不存在")
        return jd

    async def _get_resume(self, resume_id: int) -> Resume:
        r = (
            await self.db.execute(select(Resume).where(Resume.id == resume_id))
        ).scalar_one_or_none()
        if r is None:
            raise BusinessException(ErrorCode.RESUME_NOT_FOUND, f"简历 {resume_id} 不存在")
        return r

    async def _get_customization(self, customization_id: int) -> Customization:
        c = (
            await self.db.execute(
                select(Customization).where(Customization.id == customization_id)
            )
        ).scalar_one_or_none()
        if c is None:
            raise BusinessException(
                ErrorCode.CUSTOMIZATION_NOT_FOUND,
                f"定制化任务 {customization_id} 不存在",
            )
        return c
