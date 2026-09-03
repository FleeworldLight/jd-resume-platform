"""JD API。

设计文档 §7：POST /text + /url、GET 列表/详情/状态、DELETE。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_llm_service
from app.core.rate_limit import limiter
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
@limiter.limit("10/minute")
async def submit_jd_text(
    request: Request,
    body: JdTextRequest,
    service: JdService = Depends(_service),
) -> Result[JdResponse]:
    jd = await service.create_from_text(body.text)
    return Result.ok(JdResponse.model_validate(jd))


@router.post("/url", response_model=Result[JdResponse])
@limiter.limit("2/second")
async def submit_jd_url(
    request: Request,
    body: JdUrlRequest,
    service: JdService = Depends(_service),
) -> Result[JdResponse]:
    jd = await service.create_from_url(body.url)
    # Celery 触发：失败降级为同步抓取（开发环境友好）
    try:
        from app.tasks.jd_tasks import crawl_jd_task

        crawl_jd_task.delay(jd.id)
    except Exception:  # noqa: BLE001
        # broker 没起，直接同步跑
        await service.crawl_and_update(jd.id)
        jd = await service.get(jd.id)
    return Result.ok(JdResponse.model_validate(jd))


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
