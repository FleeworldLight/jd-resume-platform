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

    # —— 定制说明：只讲「改了什么 / 还差什么」，简历正文在另一份文件里 ——
    notes = customized.get("tailor_notes") or []
    suggestions = customized.get("suggestions") or []
    ranking = customized.get("ranking") or []
    tailor: list[Any] = []
    if notes:
        tailor.append(Paragraph("<b>本次做了什么</b>", _S["body"]))
        tailor += _bullets(notes)
    if ranking:
        tailor.append(Paragraph("<b>经历与岗位相关度</b>", _S["body"]))
        for r in ranking[:10]:
            hit = "、".join(r.get("matched_skills") or []) or "无直接命中"
            tailor.append(
                Paragraph(
                    f"• [{r.get('score', 0)} 分] {_esc(r.get('title', ''))}（{_esc(hit)}）",
                    _S["body"],
                )
            )
    if suggestions:
        pending = [s for s in suggestions if not s.get("confirmed")]
        tailor.append(
            Paragraph(
                f"<b>待确认的补充建议：{len(pending)} 项未确认 / 共 {len(suggestions)} 项</b>",
                _S["body"],
            )
        )
        for s in suggestions:
            tag = "已确认" if s.get("confirmed") else "未证实·待确认"
            tailor.append(
                Paragraph(
                    f"• [{_esc(s.get('priority', ''))}][{tag}] "
                    f"{_esc(s.get('skill', ''))} → {_esc(s.get('target_label', ''))}",
                    _S["body"],
                )
            )
            if s.get("text"):
                tailor.append(
                    Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;{_esc(s['text'])}", _S["body"])
                )
            if s.get("reason"):
                tailor.append(
                    Paragraph(
                        f"&nbsp;&nbsp;&nbsp;&nbsp;依据：{_esc(s['reason'])}", _S["body"]
                    )
                )
    if not tailor:
        tailor.append(
            Paragraph(
                "本条记录生成于旧版（报告格式），缺少定制说明字段；"
                "重新发起一次定制化即可得到新版产物。",
                _S["body"],
            )
        )

    story: list[Any] = [
        Paragraph(f"定制化分析报告 #{c.id}", _S["title"]),
        Paragraph(
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
            f"状态: {_esc(c.status)} · Provider: {_esc(c.provider_used or 'default')}",
            _S["meta"],
        ),
        Paragraph("简历正文请见单独导出的「简历」PDF / DOCX，本文件只做分析。", _S["meta"]),
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
        Paragraph("2. 定制说明", _S["h1"]),
        *tailor,
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


# 简历导出用的样式（与报告区分：正文更大、行距更松）
_S_RESUME = {
    "title": ParagraphStyle("r_title", fontName=_FONT, fontSize=16, leading=22, spaceAfter=10),
    "head": ParagraphStyle("r_head", fontName=_FONT, fontSize=12, leading=18, spaceBefore=10, spaceAfter=4),
    "body": ParagraphStyle("r_body", fontName=_FONT, fontSize=10.5, leading=16.5),
    "bullet": ParagraphStyle("r_bullet", fontName=_FONT, fontSize=10.5, leading=16.5, leftIndent=10),
}


def _looks_like_heading(line: str) -> bool:
    """粗判小标题：较短、不含句末标点、不是以符号开头的列表项。"""
    s = line.strip()
    if not s or len(s) > 20:
        return False
    if s.startswith(("-", "•", "*", "·", "1", "2", "3", "4", "5")):
        return False
    return not s.endswith(("。", "，", "、", "；", "：", ".", ",", ";", ":", "!", "！"))


def render_resume_pdf(text: str, title: str = "简历") -> bytes:
    """把简历纯文本渲染为 PDF。

    只做轻量排版：短行当小标题、以 - / • 开头的行当列表项、空行当段间距。
    不追求模板级美观，但保证中文正常、内容不丢。
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=title,
    )

    story: list[Any] = []
    if title:
        story += [Paragraph(_esc(title), _S_RESUME["title"]), Spacer(1, 4)]
    for raw_line in (text or "").splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            story.append(Spacer(1, 5))
            continue
        stripped = line.strip()
        if stripped.startswith(("-", "•", "*", "·")):
            story.append(Paragraph("• " + _esc(stripped.lstrip("-•*· ")), _S_RESUME["bullet"]))
        elif _looks_like_heading(stripped):
            story.append(Paragraph(_esc(stripped), _S_RESUME["head"]))
        else:
            story.append(Paragraph(_esc(stripped), _S_RESUME["body"]))

    try:
        doc.build(story)
    except Exception as exc:  # noqa: BLE001
        raise BusinessException(
            ErrorCode.INTERNAL_ERROR, f"简历 PDF 导出失败: {exc}"
        ) from exc
    return buf.getvalue()
