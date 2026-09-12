"""规则版定制化流水线（mock provider 下的兜底）。

背景
----
项目默认 provider 是 ``mock``（离线、不发任何外部请求）。mock 只会按 schema 返回
占位值，于是定制化三步（差距分析 / 定制简历 / 押题）在默认配置下得到的是
一堆 0 和空列表，看起来就是"模块坏了"。

这里提供一套**纯规则**实现：

* :func:`analyze_gap`      把「JD 要求的技能」与「简历里体现的技能」做集合比对
* :func:`customize_resume` **只重排简历里已有的信息**，不编造任何经历
* :func:`predict_questions` 题目原文取自 JD 真实句子，STAR 只给「填空骨架」

诚实边界（重要）
----------------
1. 所有输出都带 ``extract_mode = "heuristic"``，与真实 LLM 结果区分。
2. 定制简历只把用户自己的技能 / 项目按 JD 相关度重排，**不新增任何事实**。
3. 押题的 STAR 是**占位骨架**，明确提示用户填入自己的经历，
   **绝不代写「我做了什么」**——那属于编造履历。
"""
from __future__ import annotations

import re
from typing import Any

from app.schemas.customization import (
    CustomizedResume,
    Education,
    Experience,
    ExperienceGap,
    GapReport,
    InterviewPrediction,
    MissingSkill,
    PredictedQuestion,
    StarAnswer,
)
from app.services.heuristic_extract import SKILLS, _EDU_RE

# ---------------- 简历结构解析 ----------------

_DATE_BLOCK_RE = re.compile(
    r"^(\d{4}\s*[-./]\s*\d{1,2})\s*[~\-—至到]\s*"
    r"(\d{4}\s*[-./]\s*\d{1,2}|至今|现在)\s*(.*)$"
)
_BULLET_RE = re.compile(r"^[•·▪●○*\-–—]\s*")
_TECH_LINE_RE = re.compile(r"^(技术栈|所用技术|Tech\s*Stack)\s*[:：]\s*(.+)$", re.IGNORECASE)

_EDU_SECTIONS = ("学习经历", "教育经历", "教育背景", "学习与教育")
_SECTION_WORDS = (
    "学习经历", "教育经历", "教育背景", "项目经历", "个人项目", "团队项目",
    "实习经历", "工作经历", "校园经历", "专业技能", "技能", "荣誉", "获奖",
    "证书", "自我评价", "个人总结", "个人文档", "代码",
)


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines()]


def _skill_hits(text: str) -> list[str]:
    """按词典从文本中识别技能（大小写不敏感，带英文词边界）。"""
    found: list[str] = []
    for skill in SKILLS:
        pattern = r"(?<![A-Za-z])" + re.escape(skill) + r"(?![A-Za-z])"
        if re.search(pattern, text, re.IGNORECASE) and skill not in found:
            found.append(skill)
    return found


def _jd_sections(jd_text: str) -> dict[str, str]:
    """把 JD 原文按小标题粗分成 要求 / 职责 两段。"""
    lines = _lines(jd_text)
    out = {"requirements": "", "responsibilities": "", "all": jd_text}
    buf: dict[str, list[str]] = {"requirements": [], "responsibilities": []}
    current: str | None = None
    for ln in lines:
        if not ln:
            continue
        head = ln[:10]
        if any(w in head for w in ("任职要求", "岗位要求", "任职资格", "职位要求", "招聘要求", "我们希望")):
            current = "requirements"
            continue
        if any(w in head for w in ("岗位职责", "工作职责", "职位描述", "工作内容", "岗位描述", "您将")):
            current = "responsibilities"
            continue
        if current:
            buf[current].append(ln)
    out["requirements"] = "\n".join(buf["requirements"])
    out["responsibilities"] = "\n".join(buf["responsibilities"])
    return out


def _jd_required_skills(jd_text: str) -> list[tuple[str, str, str]]:
    """返回 JD 要求的技能：``(技能, 出现位置, 证据句)``。

    出现位置取值 ``requirement`` / ``responsibility`` / ``other``，
    用作「缺失技能」优先级的依据。
    """
    sections = _jd_sections(jd_text)
    lines = _lines(jd_text)
    req_lines = set(sections["requirements"].splitlines())
    resp_lines = set(sections["responsibilities"].splitlines())

    seen: dict[str, tuple[str, str]] = {}
    for skill in _skill_hits(jd_text):
        where, evidence = "other", ""
        for ln in lines:
            pattern = r"(?<![A-Za-z])" + re.escape(skill) + r"(?![A-Za-z])"
            if not re.search(pattern, ln, re.IGNORECASE):
                continue
            evidence = ln
            where = (
                "requirement" if ln in req_lines
                else "responsibility" if ln in resp_lines
                else "other"
            )
            break
        seen[skill] = (where, evidence)
    return [(s, w, e) for s, (w, e) in seen.items()]


def _parse_resume(text: str) -> tuple[list[Experience], list[Education], list[str]]:
    """从简历文本里抽取「经历 / 教育 / 技术栈」。只做结构识别，不改写内容。"""
    lines = _lines(text)
    experiences: list[Experience] = []
    educations: list[Education] = []
    tech_stack: list[str] = []

    section = ""
    cur: dict[str, Any] | None = None
    pending_title: str | None = None

    def flush() -> None:
        nonlocal cur
        if not cur:
            return
        title = cur["title"] or cur["context"] or "经历"
        experiences.append(
            Experience(
                title=title[:40],
                company=cur["context"][:40],
                duration=cur["duration"],
                description=cur["description"],
                achievements=cur["achievements"][:12],
                tech_stack=cur["tech_stack"],
            )
        )
        cur = None

    for raw in lines:
        ln = raw.strip()
        if not ln:
            continue

        tech = _TECH_LINE_RE.match(ln)
        if tech:
            items = re.split(r"[、,，/|]+", tech.group(2))
            for it in items:
                it = it.strip()
                if it and it not in tech_stack:
                    tech_stack.append(it)
            if cur is not None:
                for it in items:
                    it = it.strip()
                    if it and it not in cur["tech_stack"]:
                        cur["tech_stack"].append(it)
            continue

        # 章节标题（短、无标点、命中词典）
        bare = ln.strip(" 　:：")
        if len(bare) <= 8 and bare in _SECTION_WORDS:
            flush()
            section = bare
            pending_title = None
            continue

        m = _DATE_BLOCK_RE.match(ln)
        if m:
            flush()
            duration = f"{m.group(1).strip()} ~ {m.group(2).strip()}"
            context = m.group(3).strip()
            if section in _EDU_SECTIONS:
                parts = context.split()
                educations.append(
                    Education(
                        school=parts[0] if parts else context,
                        major=parts[1] if len(parts) > 1 else "",
                        degree=next(
                            (d for d in ("博士", "硕士", "本科", "大专", "专科") if d in context),
                            "",
                        ),
                        duration=duration,
                    )
                )
                continue
            cur = {
                "duration": duration,
                "context": context,
                "title": None,
                "description": "",
                "achievements": [],
                "tech_stack": [],
            }
            pending_title = True
            continue

        if cur is None:
            continue

        if _BULLET_RE.match(ln):
            cur["achievements"].append(_BULLET_RE.sub("", ln).strip())
            continue

        if pending_title:
            # 日期行之后的第一条普通文本行 → 视作标题
            cur["title"] = ln
            cur["description"] = ln
            pending_title = False
            continue

        if not cur["description"]:
            cur["description"] = ln
        else:
            cur["achievements"].append(ln)

    flush()
    # 学历词可能不在同一行（如「大三 · 27届」），用全文兜底；找不到就留空，不猜
    if educations:
        whole = _EDU_RE.search(text)
        fallback = ""
        if whole:
            fallback = "" if whole.group(1) in ("学历不限", "不限学历") else whole.group(1)
        for e in educations:
            if not e.degree and fallback:
                e.degree = fallback
    return experiences, educations, tech_stack


# ---------------- 1. 差距分析 ----------------


def analyze_gap(jd_text: str, jd_skills: list[str] | None, resume_text: str) -> GapReport:
    """规则版差距分析：技能集合比对 + 学历/届别比对。"""
    resume_text = resume_text or ""
    required = _jd_required_skills(jd_text or "")
    # 结构化阶段已抽出的技能也要算作 JD 要求
    known = {s for s, _, _ in required}
    for s in jd_skills or []:
        if s not in known:
            required.append((s, "other", ""))
            known.add(s)

    resume_skills = set(_skill_hits(resume_text))
    matched = [s for s, _, _ in required if s in resume_skills]
    missing_raw = [(s, w, e) for s, w, e in required if s not in resume_skills]

    total = len(required)
    score = round(100 * len(matched) / total) if total else 0
    score = max(0, min(100, score))

    # 学历 / 届别等硬门槛，命中则不再算作差距
    _exp, educations, _tech = _parse_resume(resume_text)
    resume_edu = ""
    for e in educations:
        if e.degree:
            resume_edu = e.degree
            break
    if not resume_edu:
        m = _EDU_RE.search(resume_text)
        if m:
            resume_edu = "不限" if m.group(1) == "学历不限" else m.group(1)

    experience_gaps: list[ExperienceGap] = []
    jd_edu_line = next(
        (ln for ln in _lines(jd_text or "") if _EDU_RE.search(ln)),
        "",
    )
    edu_req = _EDU_RE.search(jd_edu_line or (jd_text or ""))
    if edu_req and resume_edu:
        need = edu_req.group(1)
        order = {"大专": 1, "专科": 1, "本科": 2, "研究生": 3, "硕士": 3, "博士": 4}
        need_v = order.get(need, 0)
        have_v = order.get(resume_edu, 0)
        if need_v and have_v and have_v < need_v:
            experience_gaps.append(
                ExperienceGap(aspect="学历", current=resume_edu, expected=need)
            )
        elif need_v and have_v and have_v >= need_v:
            pass

    if "实习" in (jd_text or "") and re.search(r"实习|在校|大三|大四|届", resume_text):
        pass  # 实习要求已满足，不算差距

    priority_map = {"requirement": "HIGH", "responsibility": "MEDIUM", "other": "LOW"}
    missing: list[MissingSkill] = []
    for s, where, evidence in missing_raw[:12]:
        reason = (
            f"JD 任职要求里出现「{evidence[:40]}」" if where == "requirement" and evidence
            else f"JD 正文提到该技能（{evidence[:40]}）" if evidence
            else "JD 提到该技能，简历未体现"
        )
        missing.append(
            MissingSkill(skill=s, priority=priority_map.get(where, "LOW"), reason=reason)
        )

    focus: list[str] = []
    for s, where, _e in missing_raw[:4]:
        focus.append(f"在项目描述里补一条与「{s}」相关的实践（哪怕是课程项目）")
    if total == 0:
        focus.append("该 JD 未识别出明确技能关键词，建议人工核对后手动发起")
    if not resume_skills:
        focus.append("简历里未识别到技术关键词，建议检查简历文本是否完整解析")

    return GapReport(
        match_score=score,
        matched_skills=matched[:30],
        missing_skills=missing,
        experience_gaps=experience_gaps,
        recommended_focus=focus[:8] or ["保持现有技能描述，重点补充量化结果"],
    )


# ---------------- 2. 定制版简历（只重排，不编造） ----------------


def customize_resume(
    jd_text: str,
    jd_position: str | None,
    resume_text: str,
    gap: GapReport,
) -> CustomizedResume:
    """按 JD 相关度重排简历里**已有**的信息；不新增任何经历。"""
    resume_text = resume_text or ""
    experiences, educations, tech_stack = _parse_resume(resume_text)

    resume_skills = _skill_hits(resume_text)
    matched = [s for s in gap.matched_skills if s in resume_skills or s in tech_stack]
    others = [s for s in resume_skills if s not in matched]
    skills = (matched + others)[:30]

    position = jd_position or "目标岗位"
    if matched:
        covered = "、".join(matched[:6])
        summary = (
            f"面向「{position}」的定制版本：简历已体现 {covered}，"
            f"对岗位技能要求的覆盖度约 {gap.match_score}%。"
        )
    elif not gap.matched_skills and not gap.missing_skills:
        # JD 里没抽出可比对的要求（纯业务岗 / 文本过短），别把锅甩给简历
        summary = (
            f"面向「{position}」的定制版本：该 JD 未识别出可比的技能关键词"
            f"（可能是纯业务岗或正文过短），无法计算技能覆盖度，建议人工核对岗位要求。"
        )
    else:
        summary = (
            f"面向「{position}」的定制版本：简历里暂未识别到与岗位直接对应的技能关键词，"
            f"覆盖度 {gap.match_score}%。"
        )
    summary += (
        "建议先按下方「建议重点」补足缺失项，再投递。"
        if gap.missing_skills
        else "技能覆盖较完整，建议进一步补充量化成果。"
    )

    highlights: list[str] = []
    for s in matched[:5]:
        highlights.append(f"已覆盖岗位要求：{s}")
    for m in gap.missing_skills[:3]:
        highlights.append(f"待补足：{m.skill}（{m.priority}）")

    return CustomizedResume(
        summary=summary,
        skills=skills,
        experiences=experiences[:8],
        education=educations[:4],
        highlights=highlights[:10],
    )


# ---------------- 3. 押题（题目取自 JD 原文，STAR 只给骨架） ----------------


def _star(skill: str, hints: str) -> StarAnswer:
    """STAR 占位骨架——明确让用户填自己的经历，绝不代写。"""
    return StarAnswer(
        situation="（填背景：哪段项目/实习、团队规模、时间）",
        task=f"（填目标：你当时要解决什么问题、有什么约束{hints}）",
        action=f"（填动作：你具体怎么做的，重点写与「{skill}」相关的选型与取舍）",
        result="（填结果：最好量化，如性能提升 x%、覆盖 y 张表、上线时间）",
    )


def predict_questions(
    jd_text: str,
    jd_position: str | None,
    gap: GapReport | None = None,
    count: int = 5,
) -> InterviewPrediction:
    """从 JD 真实句子派生面试题。缺失技能优先（更容易被追问）。

    ``gap`` 为 None 时退化为「只按 JD 职责句出题」，不猜测用户缺什么。
    """
    questions: list[PredictedQuestion] = []
    evidence: dict[str, str] = {}
    for s, _w, e in _jd_required_skills(jd_text or ""):
        evidence[s] = e

    missing = [m.skill for m in gap.missing_skills] if gap else []
    matched = list(gap.matched_skills) if gap else []

    # 1) 缺失技能 → 高压追问
    for s in missing:
        ev = evidence.get(s, "")
        questions.append(
            PredictedQuestion(
                category="技能追问",
                difficulty="HARD",
                question=f"岗位要求「{s}」，但你的简历里没有直接体现。请说明你对该技能的掌握程度，以及你打算如何补齐？",
                star_answer=_star(s, f"，并且要覆盖「{ev[:30]}」这一点" if ev else ""),
                key_points=[p for p in (s, ev[:60]) if p],
                hit_reason=f"JD 提到「{s}」而简历未体现，面试官大概率会追问" if ev
                else f"JD 提到「{s}」而简历未体现",
            )
        )

    # 2) 已匹配技能 → 深挖项目细节
    for s in matched:
        ev = evidence.get(s, "")
        questions.append(
            PredictedQuestion(
                category="项目深挖",
                difficulty="MEDIUM",
                question=f"你在项目里是怎么使用 {s} 的？遇到过什么坑，怎么解决的？",
                star_answer=_star(s, ""),
                key_points=[p for p in (s, ev[:60]) if p],
                hit_reason=f"「{s}」同时出现在 JD 要求与你的简历里，是最可能被深挖的点",
            )
        )

    # 3) JD 职责句 → 通用行为面
    sections = _jd_sections(jd_text or "")
    for ln in _lines(sections["responsibilities"])[:6]:
        clean = _BULLET_RE.sub("", ln).strip()
        clean = re.sub(r"^\d+[.、)]\s*", "", clean)
        if len(clean) < 12:
            continue
        questions.append(
            PredictedQuestion(
                category="岗位理解",
                difficulty="MEDIUM",
                question=f"岗位职责里提到「{clean[:46]}」，你过往哪段经历能证明你做得到？",
                star_answer=_star("该职责", ""),
                key_points=[clean[:70]],
                hit_reason="直接对应 JD 的岗位职责原文",
            )
        )

    # 去重 + 截断
    seen: set[str] = set()
    ordered: list[PredictedQuestion] = []
    for q in questions:
        if q.question in seen:
            continue
        seen.add(q.question)
        ordered.append(q)
    return InterviewPrediction(questions=ordered[: max(1, count)])
