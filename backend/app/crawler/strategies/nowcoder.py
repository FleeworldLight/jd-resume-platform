"""牛客（nowcoder）JD 爬虫。

设计文档 §9.4：UA 池轮换 + 失败指数退避 + 单 IP 限流。
"""
from __future__ import annotations

import random
import time
from pathlib import Path

import yaml
from playwright.async_api import async_playwright

from app.core.config import settings
from app.core.exceptions import BusinessException, ErrorCode
from app.core.logging import get_logger

logger = get_logger(__name__)

_UA_POOL: list[str] | None = None


def _load_ua_pool() -> list[str]:
    global _UA_POOL
    if _UA_POOL is None:
        ua_file = Path(__file__).resolve().parent.parent / "user_agents.yml"
        data = yaml.safe_load(ua_file.read_text(encoding="utf-8")) or []
        if not data:
            raise BusinessException(ErrorCode.CRAWLER_UA_EXHAUSTED, "UA 池为空")
        _UA_POOL = list(data)
    return _UA_POOL


class NowcoderCrawler:
    name = "nowcoder"

    async def crawl(self, url: str) -> str:
        ua_pool = _load_ua_pool()
        last_err: Exception | None = None
        # 1 次主抓 + 2 次重试（指数退避）
        for attempt in range(3):
            try:
                return await self._crawl_once(url, random.choice(ua_pool))
            except BusinessException:
                raise
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning(
                    "crawler.nowcoder.attempt_failed",
                    attempt=attempt + 1,
                    error=str(exc),
                )
                if attempt < 2:
                    time.sleep(1 * (2**attempt))
        raise BusinessException(
            ErrorCode.JD_CRAWL_FAILED,
            f"牛客抓取失败（重试 3 次）: {last_err}",
        )

    async def _crawl_once(self, url: str, ua: str) -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                ctx = await browser.new_context(
                    user_agent=ua,
                    viewport={"width": 1920, "height": 1080},
                    locale="zh-CN",
                )
                page = await ctx.new_page()
                await page.goto(url, wait_until="networkidle", timeout=settings.crawler_timeout_sec * 1000)
                await page.wait_for_timeout(2000)
                text = (await page.inner_text("body")) or ""
                if len(text.strip()) < 50:
                    raise BusinessException(
                        ErrorCode.JD_CRAWL_FAILED, "抓取内容过短，可能被风控"
                    )
                return text
            finally:
                await browser.close()
