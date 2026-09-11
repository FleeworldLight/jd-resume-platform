"""抓取文本清洗小工具。"""
from __future__ import annotations

# 只在正文前这么多行内寻找锚点，避免整篇扫描
MAX_SCAN_LINES = 60


def trim_leading_noise(text: str, anchor: str | None = None) -> str:
    """去掉详情页正文前面的导航噪声。

    以职位名（anchor）为锚点：详情页正文一般从职位名那一行开始，
    例如牛客页面开头是「首页 / 题库 / 面试 / 简历 / …」等导航，
    此后才出现职位名。

    找不到锚点时**原样返回**，不做任何裁剪，避免误删正文。
    """
    if not anchor or not anchor.strip():
        return text.strip()

    target = anchor.strip()
    lines = text.splitlines()
    for idx, line in enumerate(lines[:MAX_SCAN_LINES]):
        if line.strip() == target:
            return "\n".join(lines[idx:]).strip()
    return text.strip()


def clean_lines(text: str) -> list[str]:
    """按行切分并去掉空行。"""
    return [line.strip() for line in text.splitlines() if line.strip()]
