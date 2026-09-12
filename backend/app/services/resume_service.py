"""简历 Service：上传/解析/检索/删除。

设计文档 §8.1 + docs/modules/resume.md。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BusinessException, ErrorCode
from app.core.logging import get_logger
from app.db.models.customization import Customization
from app.db.models.resume import Resume
from app.db.models.resume_vector import ResumeVector

logger = get_logger(__name__)


class ResumeService:
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_TYPES = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
    }
    ALLOWED_EXT = {".pdf", ".docx", ".txt"}

    def __init__(self, db: AsyncSession, storage_dir: str | Path | None = None) -> None:
        self.db = db
        self.storage_dir = Path(storage_dir or settings.resume_storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 上传 ----------
    async def upload_and_save(self, file: UploadFile) -> Resume:
        """上传简历：校验 → 哈希 → 去重 → 落盘 → 写库 → 触发异步解析。"""
        self._validate_file(file)

        content = await file.read()
        if not content:
            raise BusinessException(ErrorCode.INVALID_PARAMS, "文件内容为空")

        content_hash = hashlib.sha256(content).hexdigest()
        existing = await self._find_by_hash(content_hash)
        if existing is not None:
            raise BusinessException(
                ErrorCode.RESUME_DUPLICATE,
                f"简历已存在，ID={existing.id}",
                data={"existing_id": existing.id},
            )

        resume = await self._save_and_create(content, file.filename or "resume", content_hash)
        logger.info("resume.uploaded", resume_id=resume.id, filename=resume.original_filename)

        # 同步解析 + 建索引（无 Celery）
        try:
            await self.parse_and_update(resume.id)
        except BusinessException as exc:
            logger.warning(
                "resume.parse_failed_on_upload",
                resume_id=resume.id,
                error=exc.message,
            )
        resume = await self.get(resume.id)
        if resume.parse_status == "COMPLETED" and resume.resume_text:
            await self._index_resume_embedding(resume.id)
        return resume

    async def _index_resume_embedding(self, resume_id: int) -> None:
        """为简历生成 embedding 并写入向量索引。

        没配 provider / 外部 API 失败都不阻断上传——直接跳过并告警。
        """
        resume = await self.get(resume_id)
        if not resume.resume_text:
            return
        try:
            from app.services.llm_service import LLMService
            from app.services.retrieval_service import RetrievalService

            llm = LLMService(self.db)
            embed_model = await llm.get_embedding_model()
            embedding = await embed_model.aembed_query(resume.resume_text)
            await RetrievalService(self.db).index_resume(
                resume.id, resume.resume_text, embedding
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "resume.index_skipped", resume_id=resume_id, error=str(exc)
            )

    def _validate_file(self, file: UploadFile) -> None:
        # content_type 可能不可靠（浏览器/客户端不同），用扩展名兜底
        ext = Path(file.filename or "").suffix.lower()
        if ext not in self.ALLOWED_EXT:
            raise BusinessException(
                ErrorCode.RESUME_UNSUPPORTED_FORMAT,
                f"不支持的文件扩展名: {ext}，仅支持 {sorted(self.ALLOWED_EXT)}",
            )
        if file.size and file.size > self.MAX_FILE_SIZE:
            raise BusinessException(
                ErrorCode.RESUME_FILE_TOO_LARGE,
                f"文件 {file.size} 字节超过 {self.MAX_FILE_SIZE // 1024 // 1024}MB",
            )

    async def _find_by_hash(self, content_hash: str) -> Resume | None:
        stmt = select(Resume).where(Resume.content_hash == content_hash).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _save_and_create(
        self, content: bytes, filename: str, content_hash: str
    ) -> Resume:
        # 先建记录拿 id
        resume = Resume(
            original_filename=filename,
            content_hash=content_hash,
            parse_status="PENDING",
        )
        self.db.add(resume)
        await self.db.flush()

        # 写文件
        file_path = self.storage_dir / f"{resume.id}_{filename}"
        try:
            file_path.write_bytes(content)
        except OSError as exc:
            await self.db.rollback()
            raise BusinessException(
                ErrorCode.STORAGE_WRITE_FAILED, f"文件写入失败: {exc}"
            ) from exc

        resume.storage_path = str(file_path)
        await self.db.commit()
        await self.db.refresh(resume)
        return resume

    # ---------- 查询 ----------
    async def get(self, resume_id: int) -> Resume:
        stmt = select(Resume).where(Resume.id == resume_id)
        resume = (await self.db.execute(stmt)).scalar_one_or_none()
        if resume is None:
            raise BusinessException(ErrorCode.RESUME_NOT_FOUND, f"简历 {resume_id} 不存在")
        return resume

    async def list(self, page: int = 1, page_size: int = 20) -> tuple[list[Resume], int]:
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size

        total = (
            await self.db.execute(select(func.count(Resume.id)))
        ).scalar_one()

        stmt = (
            select(Resume)
            .order_by(Resume.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        items = list((await self.db.execute(stmt)).scalars().all())
        return items, int(total)

    # ---------- 删除 ----------
    async def delete(self, resume_id: int) -> None:
        resume = await self.get(resume_id)

        # 关联向量
        await self.db.execute(
            delete(ResumeVector).where(ResumeVector.resume_id == resume_id)
        )

        # 关联定制化（标记 FAILED 留痕，不删）
        await self.db.execute(
            update(Customization)
            .where(Customization.base_resume_id == resume_id)
            .where(Customization.status.in_(["PENDING", "PROCESSING"]))
            .values(
                status="FAILED",
                error_message="关联简历已删除",
            )
        )

        # 删文件
        if resume.storage_path:
            p = Path(resume.storage_path)
            if p.exists():
                try:
                    p.unlink()
                except OSError as exc:
                    logger.warning("resume.file_delete_failed", path=str(p), error=str(exc))

        # 删记录
        await self.db.delete(resume)
        await self.db.commit()
        logger.info("resume.deleted", resume_id=resume_id)

    # ---------- 解析（同步版本） ----------
    async def parse_and_update(self, resume_id: int) -> None:
        """从文件解析文本，写回 resume_text 与状态。"""
        resume = await self.get(resume_id)
        if resume.parse_status == "COMPLETED" and resume.resume_text:
            return

        resume.parse_status = "PROCESSING"
        await self.db.commit()

        try:
            text = await self._extract_text(resume.storage_path, resume.original_filename)
            resume.resume_text = text
            resume.parse_status = "COMPLETED"
            resume.parse_error = None
            await self.db.commit()
            logger.info("resume.parsed", resume_id=resume_id, length=len(text))
        except BusinessException:
            resume.parse_status = "FAILED"
            await self.db.commit()
            raise
        except Exception as exc:  # noqa: BLE001
            resume.parse_status = "FAILED"
            resume.parse_error = str(exc)[:500]
            await self.db.commit()
            raise BusinessException(
                ErrorCode.RESUME_PARSE_FAILED, f"简历解析失败: {exc}"
            ) from exc

    async def reparse(self, resume_id: int) -> None:
        """强制重新解析（清空状态后重跑）+ 重建索引。"""
        resume = await self.get(resume_id)
        resume.parse_status = "PENDING"
        resume.parse_error = None
        await self.db.commit()
        await self.parse_and_update(resume_id)
        resume = await self.get(resume_id)
        if resume.parse_status == "COMPLETED" and resume.resume_text:
            await self._index_resume_embedding(resume_id)

    # ---------- 在线编辑保存 ----------
    async def update_text(self, resume_id: int, text: str) -> Resume:
        """保存「在线编辑」后的简历全文，并重建向量索引。

        注意与原始文件的区别：这里改的是 `resume_text`（解析后的可编辑文本），
        不覆盖用户上传的原文件，原文件仍可通过 /file 下载。
        """
        if not text or not text.strip():
            raise BusinessException(ErrorCode.INVALID_PARAMS, "简历内容不能为空")
        resume = await self.get(resume_id)
        resume.resume_text = text
        # 手工编辑视为已完成解析，避免前端一直轮询
        resume.parse_status = "COMPLETED"
        resume.parse_error = None
        await self.db.commit()
        await self.db.refresh(resume)
        await self._index_resume_embedding(resume_id)
        logger.info("resume.text_updated", resume_id=resume_id, length=len(text))
        return resume

    # ---------- 导出编辑后的版本 ----------
    async def export_bytes(self, resume_id: int, fmt: str) -> tuple[bytes, str, str]:
        """导出简历。返回 (内容字节, 下载文件名, media_type)。

        导出的始终是 `resume_text`（可能已被在线编辑），不是上传的原文件。
        """
        resume = await self.get(resume_id)
        text = (resume.resume_text or "").strip()
        if not text:
            raise BusinessException(
                ErrorCode.INVALID_PARAMS, "简历内容为空，无法导出（可先重新解析或在线编辑）"
            )

        stem = Path(resume.original_filename).stem or f"resume_{resume.id}"
        fmt = (fmt or "pdf").lower()

        if fmt == "txt":
            return text.encode("utf-8"), f"{stem}.txt", "text/plain; charset=utf-8"

        if fmt == "docx":
            try:
                from docx import Document
            except ImportError as exc:
                raise BusinessException(
                    ErrorCode.INTERNAL_ERROR, "缺少 python-docx，无法导出 DOCX"
                ) from exc
            from io import BytesIO as _BytesIO

            doc = Document()
            for line in text.splitlines():
                doc.add_paragraph(line)
            buf = _BytesIO()
            doc.save(buf)
            return (
                buf.getvalue(),
                f"{stem}.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        if fmt == "pdf":
            from app.utils.pdf import render_resume_pdf

            return render_resume_pdf(text, title=stem), f"{stem}.pdf", "application/pdf"

        raise BusinessException(
            ErrorCode.INVALID_PARAMS, f"不支持的导出格式: {fmt}（可选 pdf / txt / docx）"
        )

    async def _extract_text(self, storage_path: str | None, filename: str) -> str:
        if not storage_path:
            raise BusinessException(ErrorCode.STORAGE_READ_FAILED, "简历文件路径缺失")
        path = Path(storage_path)
        if not path.exists():
            raise BusinessException(ErrorCode.STORAGE_READ_FAILED, f"文件不存在: {path}")

        ext = path.suffix.lower()
        if ext == ".pdf":
            return _parse_pdf(path)
        if ext == ".docx":
            return _parse_docx(path)
        if ext == ".txt":
            return path.read_text(encoding="utf-8", errors="ignore")
        raise BusinessException(ErrorCode.RESUME_UNSUPPORTED_FORMAT, f"暂不支持解析 {ext}")

    def get_file_path(self, resume_id: int) -> str:
        """同步取文件路径（用于下载路由）。"""
        # 不查 DB，由调用方先 get()
        raise NotImplementedError("请先 get() 拿到 storage_path")


def _parse_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise BusinessException(
            ErrorCode.RESUME_PARSE_FAILED, "缺少 pypdf，请 pip install pypdf"
        ) from exc
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _parse_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise BusinessException(
            ErrorCode.RESUME_PARSE_FAILED, "缺少 python-docx，请 pip install python-docx"
        ) from exc
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs)


async def extract_text_async(file_obj: BinaryIO, ext: str) -> str:
    """工具：直接从内存流解析（不落盘）。"""
    if ext == ".txt":
        return file_obj.read().decode("utf-8", errors="ignore")
    raise BusinessException(ErrorCode.RESUME_UNSUPPORTED_FORMAT, f"暂不支持流式解析 {ext}")
