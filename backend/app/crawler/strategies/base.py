"""爬虫策略基类。"""
from __future__ import annotations

from typing import Protocol


class JdCrawler(Protocol):
    """JD 爬虫协议。"""

    async def crawl(self, url: str) -> str:
        """抓取 JD，返回原始文本。"""
        ...
