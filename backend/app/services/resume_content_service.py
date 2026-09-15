"""结构化简历的解析与渲染。

- `text_to_content()`：把纯文本简历解析成结构化模型（认不出的一律兜底保留）
- `content_to_text()`：把结构化模型渲染回纯文本，供 `resumes.resume_text` 保存

两条约定
--------
1. **round-trip 稳定**：`text_to_content(content_to_text(c)) == c`
   （反复编辑保存不会逐次漂移，有单测守着）
2. **不丢内容**：解析时认不出的行进 `extras`，认不出的小节进 `custom_sections`，
   渲染时原样写回
"""
from __future__ import annotations

import re

from app.schemas.resume_content import (
    ResumeBasics,
    ResumeContent,
    ResumeCustomSection,
    ResumeEducation,
    ResumeItem,
    ResumeProfile,
)

# ---------- 正则 ----------
PHONE_RE = re.compile(r"(?:telephone|tel|phone|电话|手机)\s*[:：]\s*([+\d][\d\s\-]{6,})", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
AGE_RE = re.compile(r"^(\d{1,2}\s*岁.{0,12})$")
JOB_TITLE_RE = re.compile(r"^(?:求职岗位|求职意向|应聘岗位|目标岗位|意向岗位|求职目标)\s*[:：]\s*(.+)$")
TECH_RE = re.compile(r"^(?:技术栈|技术要点|技能栈|相关技术)\s*[:：]\s*(.+)$")
BULLET_RE = re.compile(r"^[•·▪◦*\-–—]\s*(.+)$")
DATE_RANGE_RE = re.compile(
    r"^(\d{4}\s*[-/.]\s*\d{1,2}|\d{4})\s*[~～\-—至到]+\s*"
    r"(\d{4}\s*[-/.]\s*\d{1,2}|\d{4}|至今|现在|present)\s*(.*)$",
    re.I,
)

# 小节别名 -> 内部类型
SECTION_ALIASES: dict[str, str] = {}
for _kind, _names in {
    "education": ["学习经历", "教育背景", "教育经历", "学历", "学习与教育"],
    "experiences": ["团队项目", "实习经历", "工作经历", "项目经历", "实践经验", "实习与项目"],
    "projects": ["个人项目", "项目经验", "个人作品", "开源项目"],
    "skills": ["技能", "专业技能", "技能清单", "掌握技能"],
    "awards": ["奖项", "荣誉", "获奖情况", "证书", "奖项荣誉"],
    "summary": ["个人简介", "自我评价", "个人总结", "简介", "个人文档", "自我介绍"],
    "links": ["代码", "作品链接", "链接", "相关链接"],
    # 常见但无固定结构的栏目：保留成自定义小节（标题 + 原始行），编辑时可直接看到
    "custom": [
        "兴趣爱好", "社团经历", "校园经历", "语言能力", "培训经历",
        "科研成果", "个人优势", "获奖经历", "发表论文", "实践活动",
    ],
}.items():
    for _n in _names:
        SECTION_ALIASES[_n] = _kind

CJK = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")

# 一行到底是「标题」还是「描述」：
# 有的简历在日期行后单独写一行项目名（团队项目），有的直接把描述写在日期行下面（个人项目）。
# 判据：短、且不含句读的当作标题，否则当作描述。
TITLE_MAX_LEN = 24
SENTENCE_PUNCT = re.compile(r"[。，；;：:！？!?]")


def _looks_like_title(s: str) -> bool:
    return len(s) <= TITLE_MAX_LEN and not SENTENCE_PUNCT.search(s)


def _join_wrapped(prev: str, nxt: str) -> str:
    """合并被 PDF 换行截断的两行：中文之间直接接，其它情况补空格。"""
    if not prev:
        return nxt
    if CJK.search(prev[-1]) and CJK.search(nxt[:1]):
        return prev + nxt
    return f"{prev} {nxt}"


def _split_tokens(rest: str) -> tuple[str, str]:
    """把「组织 + 角色」拆开：第一个词是组织，其余是角色。"""
    parts = [p for p in re.split(r"\s{1,}|\|", rest.strip()) if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def text_to_content(text: str) -> ResumeContent:
    """解析纯文本简历。认不出的一律进 extras / custom_sections，绝不静默丢弃。"""
    content = ResumeContent()
    raw_lines = text.splitlines()

    section = ""            # 当前小节：education / experiences / projects / skills / awards / summary / links / custom
    custom_title = ""
    item: ResumeItem | None = None
    education: ResumeEducation | None = None
    summary_buf: list[str] = []
    description_buf: list[str] = []
    seen_name = False

    def flush_item() -> None:
        nonlocal item, description_buf
        if item is not None:
            item.description = " ".join(description_buf).strip()
            item.highlights = [h.strip() for h in item.highlights if h.strip()]
            target = content.projects if section == "projects" else content.experiences
            if any([item.title, item.org, item.role, item.description, item.highlights, item.tech_stack]):
                target.append(item)
            item = None
        description_buf = []

    def flush_education() -> None:
        nonlocal education
        if education is not None:
            education.highlights = [h.strip() for h in education.highlights if h.strip()]
            content.education.append(education)
            education = None

    def flush_summary() -> None:
        nonlocal summary_buf
        if summary_buf and section == "summary":
            content.profile.summary = _join_wrapped(
                content.profile.summary, " ".join(summary_buf).strip()
            ).strip()
        summary_buf = []

    for raw in raw_lines:
        ln = raw.rstrip()
        stripped = ln.strip()

        if not stripped:
            # 空行是段落边界：先把缓冲落盘，但保持当前小节
            flush_summary()
            continue

        # 1) 小节标题（短、无标点）
        bare = stripped.strip(" 　:：")
        if len(bare) <= 8 and bare in SECTION_ALIASES:
            flush_item()
            flush_education()
            flush_summary()
            kind = SECTION_ALIASES[bare]
            if kind == "custom":
                section = "custom"
                content.custom_sections.append(ResumeCustomSection(title=bare))
            else:
                section = kind
            custom_title = ""
            continue
        # 未知的短标题（如自定义小节）
        if len(bare) <= 10 and bare and not re.search(r"[，。；,;：:•·]", bare) and not seen_name:
            pass  # 头部区域的行交给下面的常规规则处理

        # 2) 姓名（第一个非空行）
        if not seen_name:
            content.basics.name = stripped
            seen_name = True
            continue

        # 3) 求职岗位行
        m = JOB_TITLE_RE.match(stripped)
        if m:
            rest = m.group(1).strip()
            if "|" in rest:
                title, tagline = rest.split("|", 1)
                content.profile.title = title.strip()
                content.profile.tagline = tagline.strip()
            elif "｜" in rest:
                title, tagline = rest.split("｜", 1)
                content.profile.title = title.strip()
                content.profile.tagline = tagline.strip()
            else:
                content.profile.title = rest
            continue

        # 4) 年龄等短标识行
        m = AGE_RE.match(stripped)
        if m:
            content.basics.age = m.group(1).strip()
            continue

        # 5) 联系方式行（电话/邮箱）
        phone = PHONE_RE.search(stripped)
        email = EMAIL_RE.search(stripped)
        if phone or email:
            if phone:
                content.basics.phone = phone.group(1).strip()
            if email and not content.basics.email:
                content.basics.email = email.group(0).strip()
            if not phone and not email:
                pass
            continue

        # 6) 技术栈行
        m = TECH_RE.match(stripped)
        if m:
            items = [s.strip() for s in re.split(r"[、,，/|]+", m.group(1)) if s.strip()]
            if item is not None:
                for it in items:
                    if it not in item.tech_stack:
                        item.tech_stack.append(it)
            else:
                for it in items:
                    if it not in content.skills:
                        content.skills.append(it)
            continue

        # 7) 要点行
        m = BULLET_RE.match(stripped)
        if m:
            body = m.group(1).strip()
            if section == "projects" or section == "experiences":
                if item is None:
                    item = ResumeItem()
                item.highlights.append(body)
            elif section == "education":
                if education is None:
                    education = ResumeEducation()
                education.highlights.append(body)
            elif section == "summary":
                content.profile.highlights.append(body)
            elif section == "awards":
                content.awards.append(body)
            else:
                content.extras.append(f"• {body}")
            continue

        # 8) 日期开头 = 新条目（教育 / 经历）
        m = DATE_RANGE_RE.match(stripped)
        if m:
            start, end, rest = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            if section == "education":
                flush_education()
                tokens = [t for t in re.split(r"\s{1,}", rest) if t]
                education = ResumeEducation(
                    start=start,
                    end=end,
                    school=tokens[0] if tokens else "",
                    major=" ".join(tokens[1:]) if len(tokens) > 1 else "",
                )
            else:
                flush_item()
                if section not in ("projects", "experiences"):
                    section = "experiences"
                org, role = _split_tokens(rest)
                item = ResumeItem(start=start, end=end, org=org, role=role)
            continue

        # 9) 各小节内的普通行
        if section == "links":
            content.basics.links.append(stripped)
            continue
        if section == "summary":
            summary_buf.append(stripped)
            continue
        if section == "skills":
            for s in [x.strip() for x in re.split(r"[、,，/|]+", stripped) if x.strip()]:
                if s not in content.skills:
                    content.skills.append(s)
            continue
        if section == "awards":
            content.awards.append(stripped)
            continue
        if section in ("projects", "experiences"):
            if item is None:
                item = ResumeItem()
            if not item.title and _looks_like_title(stripped):
                item.title = stripped
            else:
                description_buf.append(stripped)
            continue
        if section == "custom":
            if content.custom_sections:
                content.custom_sections[-1].lines.append(stripped)
            else:
                content.extras.append(stripped)
            continue
        if section == "education":
            if education is None:
                education = ResumeEducation()
            if not education.school:
                education.school = stripped
            else:
                education.highlights.append(stripped)
            continue

        # 10) 兜底：认不出的行进 extras（渲染时原样写回）
        content.extras.append(stripped)

    flush_item()
    flush_education()
    flush_summary()

    # 解析质量提示：有多少行进了兜底区
    total = len([l for l in raw_lines if l.strip()])
    kept = len(content.extras)
    if kept:
        content.parse_note = (
            f"有 {kept} 行未能自动归类（共 {total} 行），已放入「其他」区，"
            f"保存时会原样写回，不会丢失。"
        )
    else:
        content.parse_note = f"共 {total} 行内容已全部归类。"
    return content


def content_to_text(c: ResumeContent) -> str:
    """把结构化简历渲染回纯文本。与 text_to_content 互为逆运算。"""
    out: list[str] = []

    if c.basics.name:
        out.append(c.basics.name)

    if c.profile.title or c.profile.tagline:
        line = f"求职岗位：{c.profile.title}"
        if c.profile.tagline:
            line += f" | {c.profile.tagline}"
        out.append(line)

    if c.basics.age:
        out.append(c.basics.age)

    contact: list[str] = []
    if c.basics.phone:
        contact.append(f"Telephone：{c.basics.phone}")
    if c.basics.email:
        contact.append(f"Email：{c.basics.email}")
    if c.basics.city:
        contact.append(f"城市：{c.basics.city}")
    if contact:
        out.append(" | ".join(contact))

    if c.basics.links:
        out.append("代码")
        out.extend(c.basics.links)

    if c.profile.summary or c.profile.highlights:
        out.append("个人文档")
        if c.profile.summary:
            out.append(c.profile.summary)
        out.extend(f"• {h}" for h in c.profile.highlights)

    if c.extras:
        out.append("其他")
        out.extend(c.extras)

    if c.education:
        out.append("学习经历")
        for e in c.education:
            left = f"{e.start} ~ {e.end}".strip(" ~") if (e.start or e.end) else ""
            mid = " ".join(x for x in [e.school, e.major, e.degree] if x)
            out.append(f"{left} {mid}".strip())
            out.extend(f"• {h}" for h in e.highlights)

    def render_items(items: list[ResumeItem], heading: str) -> None:
        if not items:
            return
        out.append(heading)
        for it in items:
            left = f"{it.start} ~ {it.end}".strip(" ~") if (it.start or it.end) else ""
            meta = " ".join(x for x in [it.org, it.role] if x)
            first = f"{left} {meta}".strip()
            if first:
                out.append(first)
            if it.title:
                out.append(it.title)
            if it.description:
                out.append(it.description)
            out.extend(f"• {h}" for h in it.highlights)
            if it.tech_stack:
                out.append(f"技术栈：{'、'.join(it.tech_stack)}")

    render_items(c.experiences, "团队项目")
    render_items(c.projects, "个人项目")

    if c.skills:
        out.append("技能")
        out.append("、".join(c.skills))

    if c.awards:
        out.append("奖项")
        out.extend(c.awards)

    for cs in c.custom_sections:
        out.append(cs.title)
        out.extend(cs.lines)

    return "\n".join(out).strip() + "\n"
