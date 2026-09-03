"""差距分析 Prompt（v1）。"""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

GAP_ANALYSIS_PROMPT_V1 = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "你是一位资深求职顾问。\n"
                "请根据 JD 和用户简历，输出严格的 JSON 差距分析报告。\n\n"
                "要求：\n"
                "- match_score: 0-100 整数，反映整体匹配度\n"
                "- matched_skills: 用户已具备、JD 要求的技能（字符串数组）\n"
                "- missing_skills: 用户缺失的技能；每项含 skill/priority(HIGH|MEDIUM|LOW)/reason\n"
                "- experience_gaps: 经验差距；每项含 aspect/current/expected\n"
                "- recommended_focus: 简历定制建议重点（字符串数组）"
            ),
        ),
        (
            "human",
            (
                "JD 文本：\n"
                "```\n"
                "{jd_text}\n"
                "```\n\n"
                "JD 结构化：\n"
                "{jd_structured}\n\n"
                "用户简历：\n"
                "```\n"
                "{resume_text}\n"
                "```\n\n"
                "请输出 JSON。"
            ),
        ),
    ]
)
