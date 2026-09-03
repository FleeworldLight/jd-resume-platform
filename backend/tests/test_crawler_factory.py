"""测试：爬虫 factory。"""
from __future__ import annotations

import pytest

from app.core.exceptions import BusinessException, ErrorCode
from app.crawler.factory import detect_source, get_crawler
from app.crawler.strategies.boss import BossCrawler
from app.crawler.strategies.nowcoder import NowcoderCrawler


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.nowcoder.com/jobs/detail/123", "NOWCODER"),
        ("https://nowcoder.com/jobs/456", "NOWCODER"),
        ("https://www.zhipin.com/job_detail/abc.html", "BOSS"),
        ("https://www.zhipin.com/position", "BOSS"),
        ("https://www.boos.com/jobs/1", "BOSS"),  # 拼写兼容
    ],
)
def test_detect_source_supported(url: str, expected: str) -> None:
    assert detect_source(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://www.lagou.com/jobs/123",
        "https://example.com/jobs/abc",
        "https://www.linkedin.com/jobs/view/123",
    ],
)
def test_detect_source_unsupported(url: str) -> None:
    with pytest.raises(BusinessException) as exc_info:
        detect_source(url)
    assert exc_info.value.code == ErrorCode.UNSUPPORTED_JD_SOURCE


def test_get_crawler_nowcoder() -> None:
    crawler = get_crawler("NOWCODER")
    assert isinstance(crawler, NowcoderCrawler)


def test_get_crawler_boss() -> None:
    crawler = get_crawler("BOSS")
    assert isinstance(crawler, BossCrawler)


def test_get_crawler_unknown() -> None:
    with pytest.raises(BusinessException) as exc_info:
        get_crawler("LAGOU")
    assert exc_info.value.code == ErrorCode.UNSUPPORTED_JD_SOURCE
