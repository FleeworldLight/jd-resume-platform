"""简历 API。

设计文档 §7：POST/GET/DELETE/resumes + reparse + status + file。
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.result import Result
from app.schemas.resume import (
    ResumeDetailResponse,
    ResumeList,
    ResumeResponse,
    ResumeStatusResponse,
)
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
    resume = await service.get(resume_id)
    if not resume.storage_path:
        from app.core.exceptions import BusinessException, ErrorCode

        raise BusinessException(ErrorCode.STORAGE_READ_FAILED, "文件路径缺失")
    p = Path(resume.storage_path)
    return FileResponse(str(p), filename=os.path.basename(p))
