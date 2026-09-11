# 简历模块

> **文档状态：部分过时（2026-09-11 标注）**
>
> 本文写于项目采用 Docker + PostgreSQL + pgvector + Redis + Celery 架构的阶段。
> 当前实际架构已简化为 SQLite + mock LLM provider + 无 Celery 的同步执行，详见根目录 README.md。
> 下文涉及 Docker / Postgres / pgvector / Redis / Celery / weasyprint 的段落仅作历史设计参考，不代表现状。

> 简历上传、解析、检索、删除。

---

## 1. 数据模型

```python
# app/db/models/resume.py
class Resume(Base):
    __tablename__ = "resumes"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str | None] = mapped_column(String(512))  # 本地路径
    resume_text: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)  # SHA-256
    parse_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    parse_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
```

---

## 2. 接口

```python
# app/api/resumes.py
from fastapi import APIRouter, UploadFile, File, Depends
from app.core.result import Result
from app.core.rate_limit import limiter
from app.services.resume_service import ResumeService

router = APIRouter(prefix="/api/resumes", tags=["resumes"])

@router.post("", response_model=Result[ResumeResponse])
@limiter.limit("10/minute")
async def upload_resume(
    request: Request,
    file: UploadFile = File(...),
    service: ResumeService = Depends(),
):
    resume = await service.upload_and_save(file)
    return Result.ok(ResumeResponse.from_entity(resume))

@router.get("", response_model=Result[list[ResumeResponse]])
async def list_resumes(
    page: int = 1,
    page_size: int = 20,
    service: ResumeService = Depends(),
):
    resumes, total = await service.list(page, page_size)
    return Result.ok(ResumeList(items=resumes, total=total))

@router.get("/{resume_id}", response_model=Result[ResumeResponse])
async def get_resume(resume_id: int, service: ResumeService = Depends()):
    resume = await service.get(resume_id)
    return Result.ok(ResumeResponse.from_entity(resume))

@router.delete("/{resume_id}", response_model=Result[None])
async def delete_resume(resume_id: int, service: ResumeService = Depends()):
    await service.delete(resume_id)
    return Result.ok(message="删除成功")

@router.post("/{resume_id}/reparse", response_model=Result[None])
async def reparse_resume(resume_id: int, service: ResumeService = Depends()):
    await service.reparse(resume_id)
    return Result.ok(message="重新解析任务已提交")

@router.get("/{resume_id}/status", response_model=Result[ResumeStatusResponse])
async def get_resume_status(resume_id: int, service: ResumeService = Depends()):
    status = await service.get_status(resume_id)
    return Result.ok(status)

@router.get("/{resume_id}/file")
async def download_resume_file(resume_id: int, service: ResumeService = Depends()):
    file_path = await service.get_file_path(resume_id)
    return FileResponse(file_path, filename=os.path.basename(file_path))
```

---

## 3. Service 实现

```python
# app/services/resume_service.py
import hashlib
from pathlib import Path

class ResumeService:
    def __init__(self, db: AsyncSession, storage_dir: str = "/app/data/resumes"):
        self.db = db
        self.storage_dir = Path(storage_dir)
    
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_TYPES = {"application/pdf", 
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                     "text/plain"}
    
    async def upload_and_save(self, file: UploadFile) -> Resume:
        # 1. 校验文件
        self._validate_file(file)
        
        # 2. 计算内容哈希
        content = await file.read()
        content_hash = hashlib.sha256(content).hexdigest()
        
        # 3. 检查去重
        existing = await self._find_by_hash(content_hash)
        if existing:
            raise BusinessException(ErrorCode.RESUME_DUPLICATE, 
                                    f"简历已存在，ID={existing.id}")
        
        # 4. 保存文件
        resume_id = await self._save_and_create(content, file.filename, content_hash)
        
        # 5. 触发异步解析
        parse_resume_task.delay(resume_id)
        
        return await self.get(resume_id)
    
    def _validate_file(self, file: UploadFile):
        if file.size > self.MAX_FILE_SIZE:
            raise BusinessException(ErrorCode.RESUME_FILE_TOO_LARGE,
                                    f"文件 {file.size} 超过 {self.MAX_FILE_SIZE // 1024 // 1024}MB")
        if file.content_type not in self.ALLOWED_TYPES:
            raise BusinessException(ErrorCode.RESUME_INVALID_TYPE,
                                    f"不支持的文件类型: {file.content_type}")
    
    async def _save_and_create(self, content: bytes, filename: str, hash_: str) -> int:
        # 创建 DB 记录（拿 ID）
        resume = Resume(
            original_filename=filename,
            content_hash=hash_,
            parse_status="PENDING",
        )
        self.db.add(resume)
        await self.db.flush()
        
        # 写文件
        file_path = self.storage_dir / f"{resume.id}_{filename}"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)
        
        # 更新 storage_path
        resume.storage_path = str(file_path)
        await self.db.commit()
        
        return resume.id
    
    async def parse_and_update(self, resume_id: int):
        resume = await self.get(resume_id)
        if not resume:
            raise BusinessException(ErrorCode.RESUME_NOT_FOUND)
        
        if resume.parse_status == "COMPLETED":
            return  # 已完成，跳过
        
        resume.parse_status = "PROCESSING"
        await self.db.commit()
        
        try:
            text = await self._extract_text(resume.storage_path, resume.original_filename)
            resume.resume_text = text
            resume.parse_status = "COMPLETED"
            resume.parse_error = None
            await self.db.commit()
            
            # 触发索引
            index_resume_task.delay(resume_id)
        except Exception as e:
            resume.parse_status = "FAILED"
            resume.parse_error = str(e)[:500]
            await self.db.commit()
            raise
    
    async def _extract_text(self, file_path: str, filename: str) -> str:
        """根据文件类型解析文本"""
        if filename.endswith(".pdf"):
            return await self._parse_pdf(file_path)
        elif filename.endswith(".docx"):
            return await self._parse_docx(file_path)
        else:
            return Path(file_path).read_text(encoding="utf-8")
    
    async def _parse_pdf(self, file_path: str) -> str:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        return "\n".join(page.extract_text() for page in reader.pages)
    
    async def _parse_docx(self, file_path: str) -> str:
        from docx import Document
        doc = Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs)
    
    async def delete(self, resume_id: int):
        resume = await self.get(resume_id)
        if not resume:
            return
        
        # 删除文件
        if resume.storage_path and Path(resume.storage_path).exists():
            Path(resume.storage_path).unlink()
        
        # 删除向量
        await self.db.execute(
            delete(ResumeVector).where(ResumeVector.resume_id == resume_id)
        )
        
        # 删除定制化任务（标记 FAILED 而不是删除，留痕）
        await self.db.execute(
            update(Customization)
            .where(Customization.base_resume_id == resume_id)
            .where(Customization.status.in_(["PENDING", "PROCESSING"]))
            .values(status="FAILED", error_message="关联简历已删除")
        )
        
        # 删除简历
        await self.db.delete(resume)
        await self.db.commit()
```

---

## 4. 测试用例

```python
# tests/unit/services/test_resume_service.py
import pytest

@pytest.mark.asyncio
async def test_upload_resume_success(resume_service, mock_file):
    resume = await resume_service.upload_and_save(mock_file)
    assert resume.parse_status == "PENDING"
    assert resume.content_hash is not None

@pytest.mark.asyncio
async def test_upload_resume_duplicate(resume_service, mock_file):
    await resume_service.upload_and_save(mock_file)
    with pytest.raises(BusinessException) as exc:
        await resume_service.upload_and_save(mock_file)
    assert exc.value.code == 1003

@pytest.mark.asyncio
async def test_upload_resume_too_large(resume_service):
    big_file = Mock(size=20 * 1024 * 1024)
    with pytest.raises(BusinessException) as exc:
        await resume_service.upload_and_save(big_file)
    assert exc.value.code == 1004

@pytest.mark.asyncio
async def test_parse_resume_pdf(resume_service):
    text = await resume_service._parse_pdf("tests/fixtures/sample.pdf")
    assert len(text) > 0

@pytest.mark.asyncio
async def test_delete_resume_cascade(resume_service, sample_resume):
    await resume_service.delete(sample_resume.id)
    # 验证关联的定制化任务标记为 FAILED
```

---

## 5. 面试讲点

1. **"简历去重怎么做的？"**
   > 上传时算 SHA-256 哈希，DB 加 unique 索引。同 hash 重复上传直接报错，提示用户已存在。

2. **"删除简历要处理什么？"**
   > 删文件、删向量记录、关联的定制化任务标记 FAILED（不能直接删定制化，留痕）。

3. **"为什么简历解析要异步？"**
   > 同步解析 PDF 可能 5-10 秒，影响用户体验。Celery 异步 + 前端轮询状态，体验好。

4. **"简历文件怎么存？"**
   > 本地文件存储，Docker volume 挂载。数据库存路径，文件按 `{id}_{filename}` 命名避免冲突。MinIO 过度设计，没必要。