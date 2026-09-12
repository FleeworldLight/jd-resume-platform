"""JD Service：粘贴/抓取/结构化抽取。

设计文档 §8 + docs/modules/jd.md。
"""
from __future__ import annotations

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessException, ErrorCode
from app.core.logging import get_logger
from app.crawler.factory import detect_source, get_crawler
from app.crawler.nowcoder_api import NowcoderApiClient, NowcoderJob, parse_job
from app.crawler.strategies.nowcoder import NowcoderCrawler
from app.db.models.jd import Jd
from app.prompts import JD_EXTRACT_PROMPT_V1
from app.schemas.llm_output import JdStructured
from app.services.heuristic_extract import extract_jd_heuristic
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
        # 统一重新读一次：确保对象上所有列都已加载，
        # 避免调用方把它们交给 Pydantic 序列化时触发惰性 IO。
        return await self.get(jd.id)

    async def create_from_url(self, url: str) -> Jd:
        """提交 URL：先建记录（PENDING），随后同步抓取 + 结构化。"""
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

    async def import_nowcoder_jobs(self, listing_url: str, limit: int = 10) -> list[Jd]:
        """抓取牛客校招职位列表，并导入职位详情。"""
        urls = await NowcoderCrawler().list_job_urls(listing_url, limit=limit)
        imported: list[Jd] = []
        for url in urls:
            existing = (await self.db.execute(select(Jd).where(Jd.source_url == url))).scalar_one_or_none()
            if existing is not None:
                if existing.source == "NOWCODER" and existing.crawl_status == "COMPLETED" and not existing.position:
                    existing.crawl_status = "PENDING"
                    await self.db.commit()
                    try:
                        await self.crawl_and_update(existing.id)
                    except BusinessException:
                        pass
                    existing = await self.get(existing.id)
                imported.append(existing)
                continue
            jd = await self.create_from_url(url)
            try:
                await self.crawl_and_update(jd.id)
            except BusinessException:
                jd = await self.get(jd.id)
            else:
                jd = await self.get(jd.id)
            imported.append(jd)
        return imported

    # ---------- 查询 ----------
    async def get(self, jd_id: int) -> Jd:
        stmt = select(Jd).where(Jd.id == jd_id)
        jd = (await self.db.execute(stmt)).scalar_one_or_none()
        if jd is None:
            raise BusinessException(ErrorCode.JD_NOT_FOUND, f"JD {jd_id} 不存在")
        return jd

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        *,
        keyword: str | None = None,
        city: str | None = None,
        education: str | None = None,
        source: str | None = None,
        salary_min: int | None = None,
        salary_max: int | None = None,
        salary_only: bool = False,
        sort: str = "latest",
    ) -> tuple[list[Jd], int]:
        """分页 + 筛选查询。

        所有筛选都是「宽匹配」：城市/学历用前缀包含，关键词跨
        职位名 / 公司 / 正文 三列模糊匹配。
        """
        page = max(1, page)
        page_size = max(1, min(200, page_size))
        offset = (page - 1) * page_size

        conditions = self._build_conditions(
            keyword=keyword,
            city=city,
            education=education,
            source=source,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_only=salary_only,
        )

        count_stmt = select(func.count(Jd.id))
        stmt = select(Jd)
        if conditions:
            count_stmt = count_stmt.where(*conditions)
            stmt = stmt.where(*conditions)

        total = int((await self.db.execute(count_stmt)).scalar_one())
        stmt = stmt.order_by(*self._order_by(sort)).offset(offset).limit(page_size)
        items = list((await self.db.execute(stmt)).scalars().all())
        return items, total

    @staticmethod
    def _build_conditions(
        *,
        keyword: str | None,
        city: str | None,
        education: str | None,
        source: str | None,
        salary_min: int | None,
        salary_max: int | None,
        salary_only: bool,
    ) -> list:
        conditions: list = []
        kw = (keyword or "").strip()
        if kw:
            like = f"%{kw}%"
            conditions.append(
                or_(
                    Jd.position.like(like),
                    Jd.company.like(like),
                    Jd.city.like(like),
                    Jd.raw_text.like(like),
                )
            )
        if city and city.strip():
            conditions.append(Jd.city.like(f"%{city.strip()}%"))
        if education and education.strip():
            conditions.append(Jd.education.like(f"%{education.strip()}%"))
        if source and source.strip():
            conditions.append(Jd.source == source.strip().upper())
        if salary_only:
            conditions.append(Jd.salary_min.is_not(None))
        if salary_min is not None:
            conditions.append(Jd.salary_max >= salary_min)
        if salary_max is not None:
            conditions.append(Jd.salary_min <= salary_max)
        return conditions

    @staticmethod
    def _order_by(sort: str) -> list:
        """排序键。薪资排序时把空值排到最后。"""
        if sort == "oldest":
            return [Jd.id.asc()]
        if sort == "salary_desc":
            return [
                case((Jd.salary_max.is_(None), 1), else_=0).asc(),
                Jd.salary_max.desc(),
                Jd.id.desc(),
            ]
        if sort == "salary_asc":
            return [
                case((Jd.salary_min.is_(None), 1), else_=0).asc(),
                Jd.salary_min.asc(),
                Jd.id.desc(),
            ]
        if sort == "company":
            return [Jd.company.asc(), Jd.id.desc()]
        # 默认 latest：按主键倒序，保证同批次入库时顺序稳定
        return [Jd.id.desc()]

    async def facets(self) -> dict:
        """筛选项统计：给前端下拉框与概览卡片用。"""
        total = int((await self.db.execute(select(func.count(Jd.id)))).scalar_one())

        async def _group(column, limit: int = 60) -> list[dict]:
            stmt = (
                select(column, func.count(Jd.id))
                .where(column.is_not(None))
                .where(column != "")
                .group_by(column)
                .order_by(func.count(Jd.id).desc())
                .limit(limit)
            )
            rows = (await self.db.execute(stmt)).all()
            return [{"value": r[0], "count": int(r[1])} for r in rows]

        with_salary = int(
            (
                await self.db.execute(
                    select(func.count(Jd.id)).where(Jd.salary_min.is_not(None))
                )
            ).scalar_one()
        )
        companies = int(
            (
                await self.db.execute(
                    select(func.count(func.distinct(Jd.company))).where(
                        Jd.company.is_not(None), Jd.company != ""
                    )
                )
            ).scalar_one()
        )

        buckets = [
            ("0-10K", 0, 10),
            ("10-20K", 10, 20),
            ("20-30K", 20, 30),
            ("30-50K", 30, 50),
            ("50K+", 50, 10_000),
        ]
        salary_ranges = []
        for label, lo, hi in buckets:
            n = int(
                (
                    await self.db.execute(
                        select(func.count(Jd.id)).where(
                            Jd.salary_min.is_not(None),
                            Jd.salary_min >= lo,
                            Jd.salary_min <= hi,
                        )
                    )
                ).scalar_one()
            )
            if n:
                salary_ranges.append({"value": label, "min": lo, "max": hi, "count": n})

        return {
            "total": total,
            "with_salary": with_salary,
            "companies": companies,
            "sources": await _group(Jd.source),
            "cities": await _group(Jd.city),
            "educations": await _group(Jd.education),
            "salary_ranges": salary_ranges,
        }

    # ---------- 删除 ----------
    async def delete(self, jd_id: int) -> None:
        jd = await self.get(jd_id)
        await self.db.delete(jd)
        await self.db.commit()
        logger.info("jd.deleted", jd_id=jd_id)

    # ---------- 抓取（同步） ----------
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
            metadata = getattr(strategy, "metadata", {})
            for field in ("company", "position", "salary_min", "salary_max", "city", "education", "experience"):
                value = metadata.get(field)
                if value is not None:
                    setattr(jd, field, value)
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

    # ---------- 批量抓取（牛客公开接口，同步） ----------
    async def crawl_nowcoder(
        self,
        limit: int = 60,
        keyword: str | None = None,
        recruit_type: int = 1,
    ) -> dict[str, int]:
        """调用牛客公开接口抓一批岗位并入库。

        走的是站点前端自己用的 ``square-search`` 接口，pageSize 可到 200，
        所以 60~200 条通常只需要 1 次请求，几秒内返回，适合放在 API 里同步执行。
        （更大规模的全量抓取请用 ``scripts/crawl_jobs.py --nowcoder-scope full``。）
        """
        client = NowcoderApiClient()
        want = max(1, min(600, limit))
        jobs: list[NowcoderJob] = []
        seen: set[int] = set()

        if keyword:
            for page in (1, 2, 3):
                data = await client.search(
                    page=page, page_size=200, recruit_type=recruit_type, query=keyword
                )
                items = data.get("datas") or []
                if not items:
                    break
                for item in items:
                    job = parse_job(item)
                    if job is None or job.job_id in seen:
                        continue
                    seen.add(job.job_id)
                    jobs.append(job)
                    if len(jobs) >= want:
                        break
                if len(jobs) >= want:
                    break
        else:
            jobs = await client.fetch_jobs(limit=want, recruit_type=recruit_type)

        stat = await self._upsert_nowcoder_jobs(jobs)
        total = int((await self.db.execute(select(func.count(Jd.id)))).scalar_one())
        return {"scanned": len(jobs), "total": total, **stat}

    async def _upsert_nowcoder_jobs(self, jobs: list[NowcoderJob]) -> dict[str, int]:
        """按 source_url 去重入库。接口字段权威 → 覆盖写（含空值）。

        与 ``scripts/crawl_jobs.py`` 的规则保持一致：
        接口把「薪资面议」解析成 None，必须覆盖写，否则会留下上一轮的假数据。
        """
        stat = {"inserted": 0, "updated": 0}
        for job in jobs:
            canon = job.url.split("?", 1)[0]
            existing = (
                await self.db.execute(select(Jd).where(Jd.source_url == canon).limit(1))
            ).scalar_one_or_none()

            if existing is None:
                jd = Jd(source="NOWCODER", source_url=canon, raw_text=job.raw_text)
                self.db.add(jd)
                stat["inserted"] += 1
            else:
                jd = existing
                jd.raw_text = job.raw_text
                stat["updated"] += 1

            metadata = job.to_metadata()
            for field_name in (
                "company", "position", "salary_min", "salary_max",
                "city", "education", "experience",
            ):
                setattr(jd, field_name, metadata.get(field_name))
            jd.crawl_status = "PARSED"
            jd.crawl_error = None
            jd.structured = {"crawl_meta": job.extra, "extract_mode": "crawler"}

        await self.db.commit()
        return stat

    # ---------- 结构化（LLM / 规则） ----------
    async def structure_jd(self, jd_id: int) -> None:
        """对 raw_text 做结构化抽取。

        默认 provider 是 ``mock``（离线、不发外部请求）。mock 只会按 schema
        返回占位值，抽出来全是空字段，因此这里在 mock 下改走**规则抽取**
        （app.services.heuristic_extract），保证「粘贴 JD 就能出字段」；
        一旦在「模型管理」里配置了真实 provider，会自动切回 LLM 路径。
        """
        jd = await self.get(jd_id)
        if not jd.raw_text:
            raise BusinessException(ErrorCode.INVALID_PARAMS, "JD 原文为空")

        provider = await self.llm.get_default_provider()
        extract_mode = "llm"
        if getattr(provider, "provider_type", None) == "mock":
            extract_mode = "heuristic"
            structured = extract_jd_heuristic(jd.raw_text)
            logger.info("jd.structured_by_heuristic", jd_id=jd_id)
        else:
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

        self._apply_structured(jd, structured, extract_mode)
        jd.crawl_status = "COMPLETED"
        jd.crawl_error = None
        await self.db.commit()
        # commit 之后刷新一次，保证 created_at / updated_at 等列已加载
        await self.db.refresh(jd, attribute_names=["created_at", "updated_at"])
        logger.info("jd.structured", jd_id=jd_id, mode=extract_mode)

    async def reparse(self, jd_id: int) -> Jd:
        """按当前 raw_text 重新做一次结构化（用于改配置后回填旧数据）。"""
        jd = await self.get(jd_id)
        jd.crawl_status = "PENDING"
        jd.crawl_error = None
        await self.db.commit()
        await self.structure_jd(jd_id)
        return await self.get(jd_id)

    def _apply_structured(self, jd: Jd, s: JdStructured, mode: str = "llm") -> None:
        jd.company = s.company or jd.company
        jd.position = s.position or jd.position
        jd.salary_min = s.salary_min if s.salary_min is not None else jd.salary_min
        jd.salary_max = s.salary_max if s.salary_max is not None else jd.salary_max
        jd.city = s.city or jd.city
        jd.experience = s.experience or jd.experience
        jd.education = s.education or jd.education
        jd.skills = s.skills
        jd.responsibilities = s.responsibilities
        jd.requirements = s.requirements
        # 保留抓取时写入的 crawl_meta（接口来源、薪资单位等溯源信息），
        # 否则重新结构化会把它们冲掉。
        data = s.model_dump()
        existing = jd.structured if isinstance(jd.structured, dict) else {}
        if isinstance(existing.get("crawl_meta"), dict):
            data["crawl_meta"] = existing["crawl_meta"]
        data["extract_mode"] = mode
        jd.structured = data
