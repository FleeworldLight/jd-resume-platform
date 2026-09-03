"""爬虫工厂：按 source 返回具体爬虫。"""
from __future__ import annotations

from app.core.exceptions import BusinessException, ErrorCode
from app.crawler.strategies.base import JdCrawler
from app.crawler.strategies.boss import BossCrawler
from app.crawler.strategies.nowcoder import NowcoderCrawler

# URL 子串 → source 枚举
DOMAIN_SOURCE_MAP: dict[str, str] = {
    "nowcoder": "NOWCODER",
    "zhipin": "BOSS",
    "boss": "BOSS",
    "boos": "BOSS",  # 拼写兼容
}


def detect_source(url: str) -> str:
    """从 URL 识别支持的来源。"""
    url_lower = url.lower()
    for sub, source in DOMAIN_SOURCE_MAP.items():
        if sub in url_lower:
            return source
    raise BusinessException(
        ErrorCode.UNSUPPORTED_JD_SOURCE,
        "暂不支持该 JD 来源，请粘贴 JD 文本",
    )


def get_crawler(source: str) -> JdCrawler:
    if source == "NOWCODER":
        return NowcoderCrawler()
    if source == "BOSS":
        return BossCrawler()
    raise BusinessException(
        ErrorCode.UNSUPPORTED_JD_SOURCE,
        f"不支持的来源: {source}",
    )
