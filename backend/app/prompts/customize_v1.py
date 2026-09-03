"""定制简历 Prompt（v1）。"""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

CUSTOMIZE_PROMPT_V1 = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "你是一位专业的简历优化专家。\n"
                "请根据 JD 和差距报告，重新组织用户的简历，让其更贴合 JD。\n\n"
                "要求：\n"
                "- 不允许伪造经历、项目、技术栈\n"
                "- 允许调整表述顺序、突出与 JD 相关的部分\n"
                "- summary 要针对 JD 重写\n"
                "- skills 按 JD 命中度排序\n"
                "- experiences 把与 JD 相关的放前面，相关性低的压缩\n"
                "- 项目描述增加量化数据和与 JD 相关的关键词\n\n"
                "输出严格的 JSON。"
            ),
        ),
        (
            "human",
            (
                "JD：\n"
                "```\n"
                "{jd_text}\n"
                "```\n\n"
                "原简历：\n"
                "```\n"
                "{resume_text}\n"
                "```\n\n"
                "差距报告：\n"
                "{gap_report}\n\n"
                "请输出定制版简历 JSON。"
            ),
        ),
    ]
)
