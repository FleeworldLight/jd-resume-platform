"""JD 结构化抽取 Prompt（v1）。"""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

JD_EXTRACT_PROMPT_V1 = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "你是一个招聘信息解析助手。请从用户给出的 JD 文本中提取结构化字段，"
                "严格按照 JSON Schema 输出，不要输出任何额外文字。\n"
                "若字段在文本中未出现，置为 null。\n"
                "salary 单位为人民币千元/月（如 20-40 即 salary_min=20, salary_max=40）。"
            ),
        ),
        (
            "human",
            (
                "JD 文本：\n"
                "```\n"
                "{jd_text}\n"
                "```\n\n"
                "请输出 JSON，包含字段："
                "company, position, salary_min, salary_max, city, experience, education, "
                "skills(数组), responsibilities(数组), requirements(数组)。"
            ),
        ),
    ]
)
