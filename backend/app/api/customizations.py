"""定制化 API。

设计文档 §7：POST/GET/DELETE/retry/status/pdf。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_llm_service
from app.core.rate_limit import limiter
from app.core.result import Result
from app.schemas.customization import (
    CustomizationCreateRequest,
    CustomizationDetailResponse,
    CustomizationList,
    CustomizationResponse,
    CustomizationStatusResponse,
)
from app.services.customization_service import CustomizationService
from app.services.llm_service import LLMService

router = APIRouter(prefix="/api/customizations", tags=["customizations"])


def _service(
    db: AsyncSession = Depends(get_db),
    llm: LLMService = Depends(get_llm_service),
) -> CustomizationService:
    return CustomizationService(db, llm)


@router.post("", response_model=Result[CustomizationResponse])
@limiter.limit("5/minute")
async def create_customization(
    request: Request,
    body: CustomizationCreateRequest,
    service: CustomizationService = Depends(_service),
) -> Result[CustomizationResponse]:
    c = await service.create(body.jd_id, body.base_resume_id, body.question_count)
    # Celery 触发；broker 不可用时降级为同步执行
    try:
        from app.tasks.customization_tasks import customize_resume_task

        customize_resume_task.delay(c.id)
    except Exception:  # noqa: BLE001
        await service.execute(c.id, question_count=body.question_count)
        c = await service.get(c.id)
    return Result.ok(CustomizationResponse.model_validate(c))


@router.get("", response_model=Result[CustomizationList])
async def list_customizations(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    service: CustomizationService = Depends(_service),
) -> Result[CustomizationList]:
    items, total = await service.list(page=page, page_size=page_size, status=status)
    return Result.ok(
        CustomizationList(
            items=[CustomizationResponse.model_validate(c) for c in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{customization_id}", response_model=Result[CustomizationDetailResponse])
async def get_customization(
    customization_id: int,
    service: CustomizationService = Depends(_service),
) -> Result[CustomizationDetailResponse]:
    c = await service.get(customization_id)
    return Result.ok(CustomizationDetailResponse.model_validate(c))


@router.delete("/{customization_id}", response_model=Result[None])
async def delete_customization(
    customization_id: int,
    service: CustomizationService = Depends(_service),
) -> Result[None]:
    await service.delete(customization_id)
    return Result.ok(message="删除成功")


@router.post("/{customization_id}/retry", response_model=Result[None])
async def retry_customization(
    customization_id: int,
    service: CustomizationService = Depends(_service),
) -> Result[None]:
    await service.retry(customization_id)
    # 触发一次执行
    try:
        from app.tasks.customization_tasks import customize_resume_task

        customize_resume_task.delay(customization_id)
    except Exception:  # noqa: BLE001
        await service.execute(customization_id)
    return Result.ok(message="重试任务已提交")


@router.get("/{customization_id}/status", response_model=Result[CustomizationStatusResponse])
async def get_customization_status(
    customization_id: int,
    service: CustomizationService = Depends(_service),
) -> Result[CustomizationStatusResponse]:
    c = await service.get(customization_id)
    return Result.ok(
        CustomizationStatusResponse(
            id=c.id,
            status=c.status,
            error_message=c.error_message,
            retry_count=c.retry_count,
            has_gap=c.gap_report is not None,
            has_resume=c.customized_resume is not None,
            has_prediction=c.prediction is not None,
        )
    )


@router.get("/{customization_id}/pdf")
async def export_pdf(
    customization_id: int,
    service: CustomizationService = Depends(_service),
):
    from app.utils.pdf import render_customization_pdf

    c = await service.get(customization_id)
    pdf_bytes = render_customization_pdf(c)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=customization_{customization_id}.pdf"
        },
    )
