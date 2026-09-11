"""JD API。

设计文档 §7：POST /text + /url、GET 列表/详情/状态、DELETE。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_llm_service
from app.core.result import Result
from app.schemas.jd import (
    JdList,
    JdResponse,
    JdStatusResponse,
    JdTextRequest,
    JdUrlRequest,
)
from app.services.jd_service import JdService
from app.services.llm_service import LLMService

router = APIRouter(prefix="/api/jds", tags=["jds"])


def _service(
    db: AsyncSession = Depends(get_db),
    llm: LLMService = Depends(get_llm_service),
) -> JdService:
    return JdService(db, llm)


@router.post("/text", response_model=Result[JdResponse])
async def submit_jd_text(
    body: JdTextRequest,
    service: JdService = Depends(_service),
) -> Result[JdResponse]:
    jd = await service.create_from_text(body.text)
    return Result.ok(JdResponse.model_validate(jd))


@router.post("/url", response_model=Result[JdResponse])
async def submit_jd_url(
    body: JdUrlRequest,
    service: JdService = Depends(_service),
) -> Result[JdResponse]:
    from app.core.config import settings

    if not settings.crawler_enabled:
        # 爬虫未启用：直接拒绝，提示用户粘贴
        from app.core.exceptions import BusinessException, ErrorCode

        raise BusinessException(
            ErrorCode.UNSUPPORTED_JD_SOURCE,
            "URL 抓取未启用（CRAWLER_ENABLED=0），请粘贴 JD 文本",
        )
    jd = await service.create_from_url(body.url)
    # 同步抓取（无 Celery）
    await service.crawl_and_update(jd.id)
    jd = await service.get(jd.id)
    return Result.ok(JdResponse.model_validate(jd))


@router.post("/import-nowcoder", response_model=Result[list[JdResponse]])
async def import_nowcoder_jobs(
    listing_url: str = "https://www.nowcoder.com/jobs/school/jobs",
    limit: int = 10,
    service: JdService = Depends(_service),
) -> Result[list[JdResponse]]:
    from app.core.config import settings

    if not settings.crawler_enabled:
        from app.core.exceptions import BusinessException, ErrorCode

        raise BusinessException(ErrorCode.UNSUPPORTED_JD_SOURCE, "URL 抓取未启用")
    jobs = await service.import_nowcoder_jobs(listing_url, limit=limit)
    return Result.ok([JdResponse.model_validate(job) for job in jobs])


@router.get("", response_model=Result[JdList])
async def list_jds(
    page: int = 1,
    page_size: int = 20,
    service: JdService = Depends(_service),
) -> Result[JdList]:
    items, total = await service.list(page=page, page_size=page_size)
    return Result.ok(
        JdList(
            items=[JdResponse.model_validate(j) for j in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{jd_id}", response_model=Result[JdResponse])
async def get_jd(
    jd_id: int,
    service: JdService = Depends(_service),
) -> Result[JdResponse]:
    jd = await service.get(jd_id)
    return Result.ok(JdResponse.model_validate(jd))


@router.delete("/{jd_id}", response_model=Result[None])
async def delete_jd(
    jd_id: int,
    service: JdService = Depends(_service),
) -> Result[None]:
    await service.delete(jd_id)
    return Result.ok(message="删除成功")


@router.get("/{jd_id}/status", response_model=Result[JdStatusResponse])
async def get_jd_status(
    jd_id: int,
    service: JdService = Depends(_service),
) -> Result[JdStatusResponse]:
    jd = await service.get(jd_id)
    return Result.ok(
        JdStatusResponse(
            id=jd.id,
            crawl_status=jd.crawl_status,
            crawl_error=jd.crawl_error,
            has_structured=jd.structured is not None,
        )
    )
