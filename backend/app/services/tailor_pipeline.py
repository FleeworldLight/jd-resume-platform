"""规则版「定制简历」构建 —— 产物是一份**可直接投递的简历**，不是报告。

与 ``heuristic_pipeline.customize_resume``（旧）的区别
----------------------------------------------------
旧版输出 ``CustomizedResume``：``summary`` 是「覆盖度 X%」这类报告话术，
``highlights`` 是「已覆盖 / 待补足」清单 —— 整体读起来像分析报告，
而且没有抬头（姓名/电话/邮箱），根本不能拿去投递。

本模块输出 :class:`TailoredResume`：

* ``content``      —— 一份完整的 :class:`ResumeContent`（抬头 / 求职意向 / 简介 /
  教育 / 经历 / 项目 / 技能），可直接导出 PDF / DOCX 投递；
* ``skill_groups`` —— 技能按类别分组，组内按与 JD 的相关度排序；
* ``ranking``      —— 每条经历/项目的相关度，解释「为什么这条排在前面」；
* ``suggestions``  —— JD 要求、简历完全没有的内容，**只以候选句形式**提出，
  由用户逐条确认（``confirmed=True``）后才进正文；
* ``tailor_notes`` —— 本次究竟调整了什么，透明可核查。

诚实边界（硬约束，不可放宽）
----------------------------
1. 只对原简历**已有**的事实做重排、归位、显性化；不新增经历、数字、技术栈。
2. ``summary`` 只能由原简历里出现过的事实拼装。
3. JD 要求而简历没有的技能只能进 ``suggestions``，默认未确认；
   未确认时导出会带上「〔未证实·待确认〕」标记，绝不冒充用户真实经历。
"""
from __future__ import annotations

import re

from app.schemas.customization import (
    GapReport,
    MissingSkill,
    RankingEntry,
    SkillGroup,
    Suggestion,
    TailoredResume,
)
from app.schemas.resume_content import ResumeContent, ResumeItem
from app.services.heuristic_pipeline import _skill_hits
from app.services.resume_content_service import text_to_content
from app.services.skill_taxonomy import canonical, category_of, group_skills

UNCONFIRMED_TAG = "〔未证实·待确认〕"

# 技能 → 常见用途短语。用于拼「候选句」，让用户有个可改的起点。
# 只描述该技能的典型用途，不涉及任何用户经历细节。
_SKILL_HINT: dict[str, str] = {
    "Kafka": "承接实时数据接入与流量削峰",
    "RabbitMQ": "做服务间异步解耦与削峰填谷",
    "Kubernetes": "完成服务的容器编排与弹性扩缩容",
    "Docker": "完成环境容器化与一键部署",
    "Redis": "做热点数据缓存与分布式锁",
    "Elasticsearch": "实现全文检索与日志聚合查询",
    "ClickHouse": "支撑大数据量下的即席查询与报表加速",
    "Doris": "支撑实时数仓的即席分析与多维报表",
    "HBase": "存储海量明细数据并支撑随机读写",
    "Hive": "完成离线数仓分层建模与指标计算",
    "Spark": "完成批式数据处理与指标计算",
    "Flink": "完成流式实时数据处理与窗口计算",
    "Hadoop": "搭建分布式存储与计算环境",
    "ETL": "完成数据抽取、清洗与加载全流程",
    "Python": "完成数据处理、脚本自动化与接口开发",
    "Java": "开发后端服务与业务模块",
    "SQL": "完成数据查询、口径核对与报表取数",
    "MySQL": "做业务数据建模与查询优化",
    "Linux": "完成服务部署、日志排查与运维脚本",
    "Nginx": "做反向代理、负载均衡与静态资源托管",
    "CI/CD": "打通自动化构建、测试与发布流程",
    "Jenkins": "搭建持续集成与自动发布流水线",
    "Git": "做版本管理与多人协作流程规范",
    "Prometheus": "搭建指标采集与告警",
    "Grafana": "搭建监控可视化看板",
    "微服务": "拆分业务域并定义服务间契约",
    "分布式": "处理分布式场景下的数据一致性问题",
    "高并发": "完成高并发场景下的性能优化与压测",
    "机器学习": "完成特征工程与模型训练调优",
    "深度学习": "完成模型结构设计与训练",
    "PyTorch": "完成模型训练与推理实现",
    "TensorFlow": "完成模型训练与部署",
    "NLP": "完成文本处理与语义分析",
    "RAG": "搭建检索增强的问答链路",
    "LangChain": "搭建大模型应用编排链路",
    "大模型": "完成大模型应用的调优与落地",
    "LLM": "完成大模型应用的调优与落地",
    "推荐系统": "完成召回与排序链路的实现",
}


def _fix_wrapped(text: str) -> str:
    """修复 PDF 抽取造成的「中文词被硬换行拆开」（如「项目经 验」）。"""
    if not text:
        return ""
    return re.sub(r"([\u4e00-\u9fa5])[ \t]+(?=[\u4e00-\u9fa5])", r"\1", text).strip()


def _item_text(it: ResumeItem) -> str:
    return " ".join(
        [
            it.title, it.org, it.role, it.description,
            *it.highlights, *it.tech_stack,
        ]
    )


def _item_hits(it: ResumeItem) -> list[str]:
    """该条经历命中的技能（已归一）。"""
    return sorted({canonical(s) for s in _skill_hits(_item_text(it))})


def _item_label(it: ResumeItem) -> str:
    return (it.title or it.org or "这段经历").strip()


def _normalize_items(items: list[ResumeItem]) -> None:
    """个人项目常被解析成 org=项目名、title 为空 —— 把项目名归位到 title。"""
    for it in items:
        if not it.title and it.org:
            it.title = it.org
            it.org = ""


def _rank_items(
    items: list[ResumeItem],
    required: set[str],
    section: str,
) -> list[dict]:
    """按与 JD 的相关度重排，返回 ``[{item, score, hits, section, index}]``。"""
    scored: list[dict] = []
    for old_i, it in enumerate(items):
        hits = _item_hits(it)
        inter = [h for h in hits if h in required]
        score = round(100 * len(inter) / len(required)) if required else 0
        scored.append(
            {
                "item": it,
                "score": min(100, score),
                "hits": inter,
                "section": section,
                "old_index": old_i,
            }
        )
    # 稳定排序：相关度降序，同分保持简历原有顺序
    scored.sort(key=lambda d: (-d["score"], d["old_index"]))
    for new_i, d in enumerate(scored):
        d["index"] = new_i
    return scored


def _build_summary(
    content: ResumeContent,
    position: str,
    matched: list[str],
    ranked: list[dict],
) -> str:
    """用原简历已有的事实拼装个人简介（不新增任何事实）。"""
    parts: list[str] = []

    base = _fix_wrapped(content.profile.summary or "")
    if base:
        parts.append(base if base.endswith(("。", "！", "；")) else base + "。")
    else:
        major = next((e.major for e in content.education if e.major), "")
        tag = content.profile.tagline
        if major:
            parts.append(f"{major}专业" + (f"（{tag}）" if tag else "") + "。")

    top = ranked[0] if ranked else None
    if top:
        it: ResumeItem = top["item"]
        desc = _fix_wrapped(it.description or (it.highlights[0] if it.highlights else ""))
        name = _item_label(it)
        if name and desc:
            parts.append(f"其中与「{position}」最相关的是「{name}」：{desc}")
            if not parts[-1].endswith(("。", "；")):
                parts[-1] += "。"

    if matched:
        parts.append(f"已具备岗位相关技能：{'、'.join(matched[:8])}。")

    return "".join(parts).strip()


def _collect_skills(
    content: ResumeContent,
    resume_text: str,
    matched: list[str],
) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """技能区：词典命中的技能 + 原简历技术栈里词典外的项（去重后分组）。"""
    known = [canonical(s) for s in _skill_hits(resume_text)]
    known_lower = [k.lower() for k in known]

    extra: list[str] = []
    for it in [*content.experiences, *content.projects]:
        for raw in it.tech_stack:
            t = (raw or "").strip()
            if not t:
                continue
            low = t.lower()
            # 已由词典技能覆盖（如 "Hadoop HDFS" vs "Hadoop"）就不再重复列
            if any(k in low for k in known_lower):
                continue
            if t not in extra:
                extra.append(t)

    skills = known + extra
    return skills, group_skills(skills, priority=matched)


def _pick_target(
    skill: str,
    ranked: list[dict],
) -> tuple[dict | None, str]:
    """给候选句挑一个最合适的落点：同类别技能最多的那段经历。"""
    cat = category_of(skill)
    best: dict | None = None
    best_n = -1
    for d in ranked:
        n = sum(1 for h in d["hits"] if category_of(h) == cat)
        if n > best_n:
            best_n, best = n, d
    if best is None:
        return None, ""
    return best, f"{best['section']}:{best['index']}"


def _section_label(section: str) -> str:
    return {"experiences": "团队项目", "projects": "个人项目"}.get(section, "经历")


def _build_suggestions(
    position: str,
    missing: list[MissingSkill],
    ranked: list[dict],
) -> list[Suggestion]:
    """把「JD 要求但简历没有」的技能变成候选句（默认未确认）。"""
    out: list[Suggestion] = []
    for i, m in enumerate(missing, start=1):
        skill = m.skill
        target, anchor = _pick_target(skill, ranked)
        hint = _SKILL_HINT.get(canonical(skill), f"完成与 {skill} 相关的开发与调试")

        if target is not None:
            it: ResumeItem = target["item"]
            name = _item_label(it)
            label = f"{_section_label(target['section'])} · {name}"
            text = f"在「{name}」中引入 {skill}，{hint}"
        else:
            label = "技能区"
            text = f"补充与 {skill} 相关的实践：{hint}"

        out.append(
            Suggestion(
                id=f"s{i:02d}",
                target=anchor or "skills",
                target_label=label,
                skill=skill,
                text=text,
                reason=m.reason,
                priority=m.priority,
                confirmed=False,
            )
        )
    return out


def _build_notes(
    position: str,
    original_title: str,
    ranked: list[dict],
    extra_skill_count: int,
    suggestions: list[Suggestion],
) -> list[str]:
    notes: list[str] = []
    if position and position != original_title:
        notes.append(f"求职意向已对准目标岗位：{original_title or '（原简历未写）'} → {position}")
    if ranked:
        top = ranked[0]
        if top["hits"]:
            notes.append(
                f"经历按岗位相关度重排，「{_item_label(top['item'])}」排在最前"
                f"（命中 {'、'.join(top['hits'][:6])}）"
            )
        else:
            notes.append("岗位未抽出可比对的关键词，经历保持原顺序")
    if extra_skill_count:
        notes.append(f"技能区归拢了 {extra_skill_count} 项原简历散落在项目技术栈里的技能")
    if suggestions:
        notes.append(
            f"有 {len(suggestions)} 项岗位要求在简历里没有依据，已生成候选句，"
            f"需你逐条确认后才会写入正文（当前带「未证实·待确认」标记）"
        )
    return notes


def build_tailored_resume(
    jd_text: str,
    jd_position: str | None,
    resume_text: str,
    gap: GapReport,
) -> TailoredResume:
    """把「原简历 + JD + 差距报告」组装成一份定制后的简历。"""
    resume_text = resume_text or ""
    content = text_to_content(resume_text)
    _normalize_items(content.experiences)
    _normalize_items(content.projects)

    position = (jd_position or content.profile.title or "目标岗位").strip()
    original_title = content.profile.title

    # required 的口径必须与差距分析完全一致（包含 JD 结构化字段里抽出的技能），
    # 否则会出现「明明命中了却算 0 分」的假象
    matched = [canonical(s) for s in (gap.matched_skills or [])]
    required = set(matched) | {canonical(m.skill) for m in (gap.missing_skills or [])}

    exp_ranked = _rank_items(content.experiences, required, "experiences")
    proj_ranked = _rank_items(content.projects, required, "projects")
    ranked = sorted(
        [*exp_ranked, *proj_ranked],
        key=lambda d: (-d["score"], d["section"] != "experiences"),
    )

    content.experiences = [d["item"] for d in exp_ranked]
    content.projects = [d["item"] for d in proj_ranked]
    content.profile.title = position
    content.profile.summary = _build_summary(content, position, matched, ranked)

    skills, groups = _collect_skills(content, resume_text, matched)
    content.skills = skills

    suggestions = _build_suggestions(position, gap.missing_skills or [], ranked)
    ranking = [
        RankingEntry(
            section=d["section"],
            index=d["index"],
            title=_item_label(d["item"]),
            score=d["score"],
            matched_skills=d["hits"][:10],
        )
        for d in ranked
    ]
    extra_skill_count = len(skills) - len({canonical(s) for s in _skill_hits(resume_text)})

    return TailoredResume(
        content=content,
        target_position=position,
        skill_groups=[SkillGroup(category=cat, items=items) for cat, items in groups],
        tailor_notes=_build_notes(
            position, original_title, ranked, extra_skill_count, suggestions
        ),
        suggestions=suggestions,
        ranking=ranking,
    )


# ---------------- 渲染成纯文本（PDF / DOCX / TXT 共用同一份排版） ----------------


def _suggestions_for(t: TailoredResume, section: str, index: int) -> list[Suggestion]:
    anchor = f"{section}:{index}"
    return [s for s in t.suggestions if s.target == anchor]


def tailored_to_text(t: TailoredResume, include_unconfirmed: bool = True) -> str:
    """把定制简历渲染成规范的简历纯文本。

    ``include_unconfirmed=True`` 时，未确认的候选句会以
    ``〔未证实·待确认〕`` 标记行插在对应位置；已确认的则作为正常内容写入。
    """
    c = t.content
    out: list[str] = []

    # —— 抬头 ——
    if c.basics.name:
        out.append(c.basics.name)
    head = f"求职岗位：{t.target_position or c.profile.title}"
    if c.profile.tagline:
        head += f" | {c.profile.tagline}"
    out.append(head)
    if c.basics.age:
        out.append(c.basics.age)
    contact = []
    if c.basics.phone:
        contact.append(f"Telephone：{c.basics.phone}")
    if c.basics.email:
        contact.append(f"Email：{c.basics.email}")
    if c.basics.city:
        contact.append(f"城市：{c.basics.city}")
    if contact:
        out.append(" | ".join(contact))
    if c.basics.links:
        out.append(" | ".join(c.basics.links))

    # —— 个人简介 ——
    if c.profile.summary:
        out.append("个人简介")
        for ln in c.profile.summary.splitlines():
            if ln.strip():
                out.append(ln.strip())
        for s in [x for x in t.suggestions if x.target == "summary"]:
            if s.confirmed:
                out.append(s.text)
            elif include_unconfirmed:
                out.append(f"{UNCONFIRMED_TAG} {s.text}")

    # —— 教育 ——
    if c.education:
        out.append("教育经历")
        for e in c.education:
            span = f"{e.start} ~ {e.end}".strip(" ~") if (e.start or e.end) else ""
            mid = " ".join(x for x in [e.school, e.major, e.degree] if x)
            out.append(f"{span} {mid}".strip())
            out.extend(f"• {h}" for h in e.highlights)

    # —— 技能（分组） ——
    if t.skill_groups:
        out.append("专业技能")
        for g in t.skill_groups:
            out.append(f"{g.category}：{'、'.join(g.items)}")

    # —— 经历 / 项目 ——
    def render(items: list[ResumeItem], heading: str, section: str) -> None:
        if not items:
            return
        out.append(heading)
        for i, it in enumerate(items):
            span = f"{it.start} ~ {it.end}".strip(" ~") if (it.start or it.end) else ""
            meta = " ".join(x for x in [it.org, it.role] if x)
            head_line = " ".join(x for x in [span, _fix_wrapped(it.title)] if x)
            if meta:
                head_line = f"{head_line} {meta}".strip()
            if head_line:
                out.append(head_line)
            if it.description:
                out.append(_fix_wrapped(it.description))
            out.extend(f"• {_fix_wrapped(h)}" for h in it.highlights if h.strip())
            if it.tech_stack:
                out.append(f"技术栈：{'、'.join(it.tech_stack)}")
            for s in _suggestions_for(t, section, i):
                if s.confirmed:
                    out.append(f"• {s.text}")
                elif include_unconfirmed:
                    out.append(f"• {UNCONFIRMED_TAG} {s.text}")

    render(c.experiences, "团队项目", "experiences")
    render(c.projects, "个人项目", "projects")

    if c.awards:
        out.append("奖项荣誉")
        out.extend(f"• {a}" for a in c.awards)

    for cs in c.custom_sections:
        out.append(cs.title)
        out.extend(cs.lines)

    # —— 仍未落位的候选句单独列出，避免丢失 ——
    orphans = [s for s in t.suggestions if s.target == "skills"]
    if include_unconfirmed and orphans:
        out.append("待确认补充项（确认后并入上方对应位置）")
        for s in orphans:
            if not s.confirmed:
                out.append(f"• {UNCONFIRMED_TAG} {s.text}")

    return "\n".join(out).strip() + "\n"
