"""定制化 API。

产物形态（2026-09 改版）：**一份简历** + **一份分析报告**，两个独立文件。
旧版把简历和分析塞进同一份「定制化报告」里，用户拿到的不是能投递的东西。

* ``POST   /api/customizations``                  发起定制化
* ``GET    /api/customizations``                  列表
* ``GET    /api/customizations/{id}``             详情（含简历纯文本预览）
* ``DELETE /api/customizations/{id}``             删除
* ``POST   /api/customizations/{id}/retry``       重试
* ``GET    /api/customizations/{id}/status``      状态
* ``POST   /api/customizations/{id}/suggestions`` 逐条确认 / 驳回「补足建议」
* ``GET    /api/customizations/{id}/pdf``         **简历 PDF**（可直接投递）
* ``GET    /api/customizations/{id}/docx``        **简历 DOCX**（可再编辑）
* ``GET    /api/customizations/{id}/report.pdf``  分析报告 PDF（差距 / 押题 / 指标）
"""
from __future__ import annotations

import re
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_llm_service
from app.core.exceptions import BusinessException, ErrorCode
from app.core.result import Result
from app.db.models.customization import Customization
from app.schemas.customization import (
    CustomizationCreateRequest,
    CustomizationDetailResponse,
    CustomizationList,
    CustomizationResponse,
    CustomizationStatusResponse,
    SuggestionApplyRequest,
    TailoredResume,
)
from app.services.customization_service import CustomizationService
from app.services.llm_service import LLMService

router = APIRouter(prefix="/api/customizations", tags=["customizations"])

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _service(
    db: AsyncSession = Depends(get_db),
    llm: LLMService = Depends(get_llm_service),
) -> CustomizationService:
    return CustomizationService(db, llm)


def _tailored(c: Customization) -> TailoredResume | None:
    """把落库的 ``customized_resume`` 还原成 :class:`TailoredResume`。

    旧记录是「报告格式」（没有 ``content`` 键）→ 返回 None，由调用方提示重跑。
    """
    data = c.customized_resume or {}
    if not isinstance(data, dict) or not data.get("content"):
        return None
    try:
        return TailoredResume.model_validate(data)
    except Exception:  # noqa: BLE001 - 结构对不上就当作旧格式
        return None


def _require_tailored(c: Customization) -> TailoredResume:
    t = _tailored(c)
    if t is None:
        raise BusinessException(
            ErrorCode.CUSTOMIZATION_INVALID_INPUT,
            "该记录是旧版「报告格式」，不含简历正文；请重新发起一次定制化。",
        )
    return t


def _stem(c: Customization) -> str:
    """文件名主干：``姓名_简历_目标岗位``。"""
    t = _tailored(c)
    parts: list[str] = []
    if t is not None:
        if t.content.basics.name:
            parts.append(t.content.basics.name)
        parts.append("简历")
        if t.target_position:
            parts.append(t.target_position)
    if not parts:
        parts = [f"定制简历_{c.id}"]
    stem = "_".join(parts)
    return re.sub(r'[\\/:*?"<>|\s]+', "_", stem).strip("_")[:60] or f"定制简历_{c.id}"


def _attachment(payload: bytes, stem: str, ext: str, media_type: str) -> Response:
    """带中文文件名的附件响应（ASCII 兜底 + RFC 5987 的 UTF-8 名）。"""
    filename = f"{stem}.{ext}"
    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="customization.{ext}"; '
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )


def _detail(c: Customization) -> CustomizationDetailResponse:
    resp = CustomizationDetailResponse.model_validate(c)
    t = _tailored(c)
    if t is not None:
        from app.services.tailor_pipeline import tailored_to_text

        resp.resume_text = tailored_to_text(t, include_unconfirmed=True)
    return resp


@router.post("", response_model=Result[CustomizationResponse])
async def create_customization(
    body: CustomizationCreateRequest,
    service: CustomizationService = Depends(_service),
) -> Result[CustomizationResponse]:
    c = await service.create(body.jd_id, body.base_resume_id, body.question_count)
    # 同步执行完整流水线（无 Celery），本地可能耗时数十秒
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
    return Result.ok(_detail(c))


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
    # 同步重跑一次
    await service.execute(customization_id)
    return Result.ok(message="重试成功")


@router.get("/{customization_id}/status", response_model=Result[CustomizationStatusResponse])
async def get_customization_status(
    customization_id: int,
    service: CustomizationService = Depends(_service),
) -> Result[CustomizationStatusResponse]:
    c = await service.get(customization_id)
    data = c.customized_resume or {}
    items = data.get("suggestions") or [] if isinstance(data, dict) else []
    return Result.ok(
        CustomizationStatusResponse(
            id=c.id,
            status=c.status,
            error_message=c.error_message,
            retry_count=c.retry_count,
            has_gap=c.gap_report is not None,
            has_resume=c.customized_resume is not None,
            has_prediction=c.prediction is not None,
            suggestion_total=len(items),
            suggestion_confirmed=sum(1 for s in items if s.get("confirmed")),
        )
    )


@router.post(
    "/{customization_id}/suggestions",
    response_model=Result[CustomizationDetailResponse],
)
async def update_suggestions(
    customization_id: int,
    body: SuggestionApplyRequest,
    service: CustomizationService = Depends(_service),
) -> Result[CustomizationDetailResponse]:
    """逐条确认（或驳回）「补足建议」。``ids`` 为空表示全部。"""
    c = await service.set_suggestions(customization_id, body.ids, body.confirmed)
    return Result.ok(_detail(c))


@router.get("/{customization_id}/pdf")
async def export_resume_pdf(
    customization_id: int,
    service: CustomizationService = Depends(_service),
) -> Response:
    """导出**简历** PDF —— 可直接投递。

    未确认的候选句会带「〔未证实·待确认〕」标记，已确认的作为正常内容。
    """
    from app.services.tailor_pipeline import tailored_to_text
    from app.utils.pdf import render_resume_pdf

    c = await service.get(customization_id)
    t = _require_tailored(c)
    text = tailored_to_text(t, include_unconfirmed=True)
    # title 传空：正文第一行已经是姓名，避免抬头重复
    return _attachment(render_resume_pdf(text, title=""), _stem(c), "pdf", "application/pdf")


@router.get("/{customization_id}/docx")
async def export_resume_docx(
    customization_id: int,
    service: CustomizationService = Depends(_service),
) -> Response:
    """导出**简历** DOCX（可继续用 Word / WPS 编辑）。"""
    from app.services.tailor_pipeline import tailored_to_text
    from app.utils.docx import render_text_docx

    c = await service.get(customization_id)
    t = _require_tailored(c)
    text = tailored_to_text(t, include_unconfirmed=True)
    return _attachment(render_text_docx(text, title=""), _stem(c), "docx", DOCX_MIME)


@router.get("/{customization_id}/report.pdf")
async def export_report_pdf(
    customization_id: int,
    service: CustomizationService = Depends(_service),
) -> Response:
    """导出**分析报告** PDF（差距分析 / 定制说明 / 面试押题 / 召回指标）。"""
    from app.utils.pdf import render_customization_pdf

    c = await service.get(customization_id)
    payload = render_customization_pdf(c)
    return _attachment(payload, f"{_stem(c)}_分析报告", "pdf", "application/pdf")
