"""PDF 渲染：定制化报告 → reportlab。

本地零外部服务：reportlab 自带中文字体映射（STSong-Light），
不依赖 weasyprint / GTK / 系统字体。
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.core.exceptions import BusinessException, ErrorCode
from app.db.models.customization import Customization

# 注册中文字体（reportlab 内置 CID 字体，无需系统字体）
_FONT = "STSong-Light"
try:
    pdfmetrics.registerFont(UnicodeCIDFont(_FONT))
except Exception:  # pragma: no cover - 字体加载失败时降级 Helvetica
    _FONT = "Helvetica"

_S = {
    "title": ParagraphStyle("title", fontName=_FONT, fontSize=18, leading=24, spaceAfter=12),
    "h1": ParagraphStyle("h1", fontName=_FONT, fontSize=14, leading=20, spaceBefore=12, spaceAfter=6),
    "meta": ParagraphStyle("meta", fontName=_FONT, fontSize=9, leading=14, textColor="#666666"),
    "body": ParagraphStyle("body", fontName=_FONT, fontSize=10.5, leading=16),
    "score": ParagraphStyle("score", fontName=_FONT, fontSize=22, leading=28, textColor="#2e7d32"),
    "small": ParagraphStyle("small", fontName=_FONT, fontSize=9.5, leading=14, textColor="#444444"),
}


def _esc(v: Any) -> str:
    """转义 XML 特殊字符（reportlab Paragraph 用 XML 标记）。"""
    return str(v if v is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _bullets(items: list[Any], key: str | None = None) -> list[str]:
    out = []
    for it in items or []:
        txt = _esc(it.get(key)) if key and isinstance(it, dict) else _esc(it)
        if txt:
            out.append(Paragraph(f"• {txt}", _S["body"]))
    return out or [Paragraph("• -", _S["body"])]


def render_customization_pdf(c: Customization) -> bytes:
    """把一条 Customization 记录渲染为 PDF 字节流。"""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        title=f"定制化报告 #{c.id}",
    )
    gap = c.gap_report or {}
    customized = c.customized_resume or {}
    prediction = c.prediction or {}
    metrics = c.retrieval_metrics or {}
    h = metrics.get("hybrid") or {}

    story: list[Any] = [
        Paragraph(f"定制化报告 #{c.id}", _S["title"]),
        Paragraph(
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
            f"状态: {_esc(c.status)} · Provider: {_esc(c.provider_used or 'default')}",
            _S["meta"],
        ),
        Spacer(1, 8),
        Paragraph("1. 差距分析", _S["h1"]),
        Paragraph(f"{gap.get('match_score', 0)} / 100", _S["score"]),
        Paragraph("<b>已匹配技能</b>", _S["body"]),
        *_bullets(gap.get("matched_skills", [])),
        Paragraph("<b>缺失技能</b>", _S["body"]),
        *_bullets(gap.get("missing_skills", []), key="skill"),
        Paragraph("<b>建议重点</b>", _S["body"]),
        *_bullets(gap.get("recommended_focus", [])),
        Spacer(1, 8),
        Paragraph("2. 定制版简历", _S["h1"]),
        Paragraph("<b>个人简介：</b>" + _esc(customized.get("summary", "")), _S["body"]),
        Paragraph("<b>核心技能：</b>" + _esc("、".join(customized.get("skills", []))), _S["body"]),
        Spacer(1, 4),
        Paragraph("3. 面试预测", _S["h1"]),
        *_render_questions(prediction.get("questions", [])),
        Spacer(1, 8),
        Paragraph("4. 召回评估", _S["h1"]),
        Paragraph(
            f"混合 Recall@10: <b>{h.get('recall_at_k', 0):.3f}</b> &nbsp; "
            f"Precision@10: <b>{h.get('precision_at_k', 0):.3f}</b>",
            _S["body"],
        ),
    ]

    try:
        doc.build(story)
    except Exception as exc:  # noqa: BLE001
        raise BusinessException(
            ErrorCode.INTERNAL_ERROR, f"PDF 导出失败: {exc}"
        ) from exc
    return buf.getvalue()


def _render_questions(questions: list[dict]) -> list[Paragraph]:
    if not questions:
        return [Paragraph("• -", _S["body"])]
    out: list[Paragraph] = []
    for q in questions:
        cat = _esc(q.get("category", ""))
        diff = _esc(q.get("difficulty", ""))
        question = _esc(q.get("question", ""))
        reason = _esc(q.get("hit_reason", ""))
        sa = q.get("star_answer") or {}
        star = " / ".join(
            _esc(sa.get(k, "")) for k in ("situation", "task", "action", "result")
        )
        kps = "；".join(_esc(k) for k in q.get("key_points", []))
        out.append(Paragraph(f"<b>[{cat} / {diff}]</b> {question}", _S["body"]))
        out.append(Paragraph(f"<i>为什么被问到: {reason}</i>", _S["small"]))
        out.append(Paragraph(f"STAR: {star}", _S["small"]))
        if kps:
            out.append(Paragraph(f"关键点: {kps}", _S["small"]))
        out.append(Spacer(1, 6))
    return out
