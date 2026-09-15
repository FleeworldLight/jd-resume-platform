"""简历 API。

设计文档 §7：POST/GET/DELETE/resumes + reparse + status + file。
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.result import Result
from app.schemas.resume import (
    ResumeDetailResponse,
    ResumeList,
    ResumeResponse,
    ResumeStatusResponse,
    ResumeUpdateRequest,
)
from app.schemas.resume_content import ResumeContent
from app.services.resume_content_service import content_to_text, text_to_content
from app.services.resume_service import ResumeService

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


def _service(db: AsyncSession = Depends(get_db)) -> ResumeService:
    return ResumeService(db)


@router.post("", response_model=Result[ResumeResponse])
async def upload_resume(
    file: UploadFile = File(...),
    service: ResumeService = Depends(_service),
) -> Result[ResumeResponse]:
    resume = await service.upload_and_save(file)
    return Result.ok(ResumeResponse.model_validate(resume))


@router.get("", response_model=Result[ResumeList])
async def list_resumes(
    page: int = 1,
    page_size: int = 20,
    service: ResumeService = Depends(_service),
) -> Result[ResumeList]:
    items, total = await service.list(page=page, page_size=page_size)
    return Result.ok(
        ResumeList(
            items=[ResumeResponse.model_validate(r) for r in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{resume_id}", response_model=Result[ResumeDetailResponse])
async def get_resume(
    resume_id: int,
    service: ResumeService = Depends(_service),
) -> Result[ResumeDetailResponse]:
    resume = await service.get(resume_id)
    return Result.ok(ResumeDetailResponse.model_validate(resume))


@router.delete("/{resume_id}", response_model=Result[None])
async def delete_resume(
    resume_id: int,
    service: ResumeService = Depends(_service),
) -> Result[None]:
    await service.delete(resume_id)
    return Result.ok(message="删除成功")


@router.post("/{resume_id}/reparse", response_model=Result[None])
async def reparse_resume(
    resume_id: int,
    service: ResumeService = Depends(_service),
) -> Result[None]:
    await service.reparse(resume_id)
    return Result.ok(message="重新解析完成")


@router.get("/{resume_id}/status", response_model=Result[ResumeStatusResponse])
async def get_resume_status(
    resume_id: int,
    service: ResumeService = Depends(_service),
) -> Result[ResumeStatusResponse]:
    resume = await service.get(resume_id)
    return Result.ok(
        ResumeStatusResponse(
            id=resume.id,
            parse_status=resume.parse_status,
            parse_error=resume.parse_error,
        )
    )


@router.get("/{resume_id}/file")
async def download_resume_file(
    resume_id: int,
    service: ResumeService = Depends(_service),
):
    """下载**上传的原文件**（不改动）。"""
    resume = await service.get(resume_id)
    if not resume.storage_path:
        from app.core.exceptions import BusinessException, ErrorCode

        raise BusinessException(ErrorCode.STORAGE_READ_FAILED, "文件路径缺失")
    p = Path(resume.storage_path)
    return FileResponse(str(p), filename=os.path.basename(p))


@router.put("/{resume_id}", response_model=Result[ResumeDetailResponse])
async def update_resume(
    resume_id: int,
    body: ResumeUpdateRequest,
    service: ResumeService = Depends(_service),
) -> Result[ResumeDetailResponse]:
    """保存在线编辑后的简历全文（写入 `resume_text`，不覆盖上传的原文件）。"""
    resume = await service.update_text(resume_id, body.resume_text)
    return Result.ok(ResumeDetailResponse.model_validate(resume))


@router.get("/{resume_id}/content", response_model=Result[ResumeContent])
async def get_resume_content(
    resume_id: int,
    service: ResumeService = Depends(_service),
) -> Result[ResumeContent]:
    """把 `resume_text` 解析成结构化内容，供编辑器表单使用。

    解析是「不丢内容」的：认不出的行进 `extras`、认不出的小节进 `custom_sections`，
    保存时会原样写回。
    """
    resume = await service.get(resume_id)
    return Result.ok(text_to_content(resume.resume_text or ""))


@router.put("/{resume_id}/content", response_model=Result[ResumeContent])
async def update_resume_content(
    resume_id: int,
    body: ResumeContent,
    service: ResumeService = Depends(_service),
) -> Result[ResumeContent]:
    """保存结构化内容。

    渲染回纯文本后写入 `resume_text`（**不覆盖上传的原文件**），
    再把落库后的文本重新解析一遍返回 —— 前端用返回值刷新表单，
    这样「用户看到的」与「实际存下来的」永远一致。
    """
    text = content_to_text(body)
    await service.update_text(resume_id, text)
    return Result.ok(text_to_content(text))


@router.get("/{resume_id}/export")
async def export_resume(
    resume_id: int,
    fmt: str = "pdf",
    service: ResumeService = Depends(_service),
):
    """导出**编辑后的简历**：pdf / txt / docx。

    与 `/file` 的区别：/file 给的是上传的原文件，这里是 `resume_text`
    （可能已经被在线编辑过）重新渲染出来的版本。
    """
    from urllib.parse import quote

    content, filename, media_type = await service.export_bytes(resume_id, fmt)
    # 文件名可能含中文，用 RFC 5987 形式，避免下载时乱码
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": disposition},
    )
