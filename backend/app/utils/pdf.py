"""PDF 渲染：定制化报告 → weasyprint。

设计文档 docs/modules/customization.md §7。
"""
from __future__ import annotations

from datetime import datetime
from html import escape

from app.core.exceptions import BusinessException, ErrorCode
from app.db.models.customization import Customization

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: "Microsoft YaHei", "PingFang SC", sans-serif; padding: 40px; color: #222; }}
  h1 {{ color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }}
  h2 {{ color: #4CAF50; margin-top: 30px; border-left: 4px solid #4CAF50; padding-left: 10px; }}
  h3 {{ color: #555; margin-top: 18px; }}
  .meta {{ color: #666; font-size: 13px; margin-bottom: 20px; }}
  .section {{ margin-bottom: 28px; }}
  .score {{ font-size: 36px; color: #4CAF50; font-weight: bold; }}
  .question {{ background: #f8f8f8; padding: 14px; margin: 12px 0; border-left: 4px solid #4CAF50; }}
  .star {{ background: #fffbf0; padding: 8px 10px; margin: 6px 0; border-radius: 4px; }}
  ul {{ margin: 6px 0 6px 22px; }}
  .priority-HIGH {{ color: #d9534f; font-weight: bold; }}
  .priority-MEDIUM {{ color: #f0ad4e; font-weight: bold; }}
  .priority-LOW {{ color: #5bc0de; }}
</style>
</head>
<body>
  <h1>定制化报告 #{customization.id}</h1>
  <p class="meta">生成时间: {generated_at} · 状态: {status} · Provider: {provider}</p>

  <div class="section">
    <h2>1. 差距分析</h2>
    <p class="score">{match_score} / 100</p>
    <h3>已匹配技能</h3>
    <ul>{matched_skills}</ul>
    <h3>缺失技能</h3>
    <ul>{missing_skills}</ul>
    <h3>建议重点</h3>
    <ul>{recommended_focus}</ul>
  </div>

  <div class="section">
    <h2>2. 定制版简历</h2>
    <h3>个人简介</h3>
    <p>{summary}</p>
    <h3>核心技能</h3>
    <p>{skills}</p>
    <h3>项目经历</h3>
    {experiences}
  </div>

  <div class="section">
    <h2>3. 面试预测</h2>
    {questions}
  </div>

  <div class="section">
    <h2>4. 召回评估</h2>
    <p>混合 Recall@10: <strong>{recall_h}</strong> &nbsp; Precision@10: <strong>{precision_h}</strong></p>
    <p>纯向量 Recall@10: <strong>{recall_v}</strong> &nbsp; 关键词 Recall@10: <strong>{recall_k}</strong></p>
  </div>
</body>
</html>"""


def render_customization_pdf(c: Customization) -> bytes:
    try:
        from weasyprint import HTML
    except OSError as exc:
        # Windows: weasyprint 缺 GTK native lib
        raise BusinessException(
            ErrorCode.INTERNAL_ERROR,
            "PDF 导出失败：weasyprint 缺少系统依赖（GTK/Pango）。Linux/Mac 正常，Windows 请先安装。",
        ) from exc
    except ImportError as exc:
        raise BusinessException(
            ErrorCode.INTERNAL_ERROR,
            f"PDF 导出失败：{exc}",
        ) from exc

    html = _build_html(c)
    return HTML(string=html).write_pdf()


def _build_html(c: Customization) -> str:
    gap = c.gap_report or {}
    customized = c.customized_resume or {}
    prediction = c.prediction or {}
    metrics = c.retrieval_metrics or {}

    matched = _li_list(gap.get("matched_skills", []))
    missing = _missing_skills_html(gap.get("missing_skills", []))
    focus = _li_list(gap.get("recommended_focus", []))

    summary = escape(customized.get("summary", ""))
    skills = escape("、".join(customized.get("skills", [])))
    experiences = _experiences_html(customized.get("experiences", []))
    questions = _questions_html(prediction.get("questions", []))

    h = metrics.get("hybrid") or {}
    v = metrics.get("vector_only") or {}
    k = metrics.get("keyword_only") or {}

    return HTML_TEMPLATE.format(
        customization=c,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        status=escape(c.status),
        provider=escape(c.provider_used or "default"),
        match_score=gap.get("match_score", 0),
        matched_skills=matched,
        missing_skills=missing,
        recommended_focus=focus,
        summary=summary,
        skills=skills,
        experiences=experiences,
        questions=questions,
        recall_h=f"{h.get('recall_at_k', 0):.3f}",
        precision_h=f"{h.get('precision_at_k', 0):.3f}",
        recall_v=f"{v.get('recall_at_k', 0):.3f}",
        recall_k=f"{k.get('recall_at_k', 0):.3f}",
    )


def _li_list(items: list[str]) -> str:
    return "".join(f"<li>{escape(s)}</li>" for s in items) or "<li>-</li>"


def _missing_skills_html(items: list[dict]) -> str:
    if not items:
        return "<li>-</li>"
    out = []
    for it in items:
        skill = escape(str(it.get("skill", "")))
        pri = str(it.get("priority", "")).upper()
        reason = escape(str(it.get("reason", "")))
        out.append(
            f'<li><span class="priority-{pri}">[{pri}]</span> <strong>{skill}</strong>'
            f' &nbsp; <span style="color:#666">{reason}</span></li>'
        )
    return "".join(out)


def _experiences_html(items: list[dict]) -> str:
    if not items:
        return "<p>-</p>"
    out = []
    for exp in items:
        title = escape(str(exp.get("title", "")))
        company = escape(str(exp.get("company", "")))
        duration = escape(str(exp.get("duration", "")))
        desc = escape(str(exp.get("description", "")))
        achvs = "".join(f"<li>{escape(a)}</li>" for a in exp.get("achievements", []))
        out.append(
            f"<h3>{title} @ {company} <small style='color:#888'>({duration})</small></h3>"
            f"<p>{desc}</p>"
            f"<ul>{achvs}</ul>"
        )
    return "".join(out)


def _questions_html(items: list[dict]) -> str:
    if not items:
        return "<p>-</p>"
    out = []
    for q in items:
        cat = escape(str(q.get("category", "")))
        diff = escape(str(q.get("difficulty", "")))
        question = escape(str(q.get("question", "")))
        reason = escape(str(q.get("hit_reason", "")))
        sa = q.get("star_answer", {}) or {}
        s = escape(str(sa.get("situation", "")))
        t = escape(str(sa.get("task", "")))
        a = escape(str(sa.get("action", "")))
        r = escape(str(sa.get("result", "")))
        kps = "".join(f"<li>{escape(k)}</li>" for k in q.get("key_points", []))
        out.append(
            f'<div class="question">'
            f'<p><strong>[{cat} / {diff}]</strong> {question}</p>'
            f'<p><em>为什么被问到: {reason}</em></p>'
            f'<div class="star"><strong>S:</strong> {s}</div>'
            f'<div class="star"><strong>T:</strong> {t}</div>'
            f'<div class="star"><strong>A:</strong> {a}</div>'
            f'<div class="star"><strong>R:</strong> {r}</div>'
            f'<p>关键点:</p><ul>{kps}</ul>'
            f'</div>'
        )
    return "".join(out)
