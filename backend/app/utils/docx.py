"""把纯文本简历渲染成 DOCX（可继续用 Word 编辑）。

为什么要 DOCX
-------------
PDF 适合直接投递，但求职季几乎一定会改内容（改岗位、改措辞、改排序）。
DOCX 让用户拿到文件后能直接在 Word/WPS 里改，而不是被迫重来。
"""
from __future__ import annotations

from io import BytesIO

from app.core.exceptions import BusinessException, ErrorCode
from app.utils.pdf import _looks_like_heading

__all__ = ["render_text_docx"]


def render_text_docx(text: str, title: str = "简历") -> bytes:
    """轻量排版：短行当小标题（加粗）、``-``/``•`` 开头当列表项、空行当段距。

    不追求模板级美观，但保证中文正常、结构清晰、内容不丢。
    """
    try:
        from docx import Document
        from docx.shared import Pt
    except ImportError as exc:  # pragma: no cover - 依赖缺失时给出明确提示
        raise BusinessException(
            ErrorCode.INTERNAL_ERROR, "缺少 python-docx，无法导出 DOCX"
        ) from exc

    doc = Document()
    try:
        doc.styles["Normal"].font.size = Pt(10.5)
    except KeyError:  # pragma: no cover - 样式表异常时不影响导出
        pass

    if title:
        head = doc.add_paragraph()
        run = head.add_run(title)
        run.bold = True
        run.font.size = Pt(15)

    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped.startswith(("-", "•", "*", "·")):
            doc.add_paragraph(stripped.lstrip("-•*· ").strip(), style="List Bullet")
            continue
        para = doc.add_paragraph()
        run = para.add_run(stripped)
        if _looks_like_heading(stripped):
            run.bold = True
            run.font.size = Pt(12)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
