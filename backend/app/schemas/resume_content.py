"""结构化简历内容模型（编辑器的数据契约）。

设计原则
--------
**往返不丢内容**：`resume_text` 是唯一事实来源，编辑器只是更友好的编辑方式。
所以模型里必须留出兜底位：

- `extras`         —— 未归类到任何小节的原文行
- `custom_sections` —— 无法识别的自定义小节（保留标题与原始行）

这样即使解析器认不出某个区块，内容也不会在「保存」时被吞掉。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ResumeBasics(BaseModel):
    """基本信息：姓名与联系方式。"""

    name: str = ""
    phone: str = ""
    email: str = ""
    city: str = ""
    age: str = ""
    links: list[str] = Field(default_factory=list)


class ResumeProfile(BaseModel):
    """求职意向 / 个人简介。"""

    title: str = ""      # 求职岗位，如「大数据开发实习」
    tagline: str = ""    # 附加身份信息，如「大三 · 27届」
    summary: str = ""    # 个人简介正文（多行会合并为一段）
    highlights: list[str] = Field(default_factory=list)  # 简介下的要点/链接列表


class ResumeItem(BaseModel):
    """一条经历/项目。字段全部可选，鼓励「认不出就留空」而不是猜。"""

    title: str = ""                 # 项目/岗位名称
    org: str = ""                   # 组织：公司 / 课程 / 团队
    role: str = ""                  # 角色，如「核心开发」
    start: str = ""
    end: str = ""
    description: str = ""           # 一句话概述
    highlights: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)


class ResumeEducation(BaseModel):
    """一段教育经历。"""

    school: str = ""
    major: str = ""
    degree: str = ""
    start: str = ""
    end: str = ""
    highlights: list[str] = Field(default_factory=list)


class ResumeCustomSection(BaseModel):
    """认不出来的自定义小节 —— 原样保留，避免保存时丢内容。"""

    title: str
    lines: list[str] = Field(default_factory=list)


class ResumeContent(BaseModel):
    """完整结构化简历。"""

    basics: ResumeBasics = Field(default_factory=ResumeBasics)
    profile: ResumeProfile = Field(default_factory=ResumeProfile)
    education: list[ResumeEducation] = Field(default_factory=list)
    experiences: list[ResumeItem] = Field(default_factory=list)  # 团队项目 / 实习 / 工作
    projects: list[ResumeItem] = Field(default_factory=list)     # 个人项目
    skills: list[str] = Field(default_factory=list)
    awards: list[str] = Field(default_factory=list)
    extras: list[str] = Field(default_factory=list)
    custom_sections: list[ResumeCustomSection] = Field(default_factory=list)

    # 供前端提示"这份简历有多少内容被识别" —— 便于用户判断有没有解析丢东西
    parse_note: str = ""
