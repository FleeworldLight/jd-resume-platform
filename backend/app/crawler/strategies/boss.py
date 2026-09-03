"""Boss 直聘（zhipin/boss）JD 爬虫。

设计文档 §9.4：UA 池轮换 + 失败指数退避。
Boss 经常要验证码，先等几秒并尝试多个选择器。
"""
from __future__ import annotations

import random
import time

from playwright.async_api import async_playwright

from app.core.config import settings
from app.core.exceptions import BusinessException, ErrorCode
from app.core.logging import get_logger
from app.crawler.strategies.nowcoder import _load_ua_pool

logger = get_logger(__name__)


class BossCrawler:
    name = "boss"

    async def crawl(self, url: str) -> str:
        ua_pool = _load_ua_pool()
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                return await self._crawl_once(url, random.choice(ua_pool))
            except BusinessException:
                raise
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning(
                    "crawler.boss.attempt_failed",
                    attempt=attempt + 1,
                    error=str(exc),
                )
                if attempt < 2:
                    time.sleep(1 * (2**attempt))
        raise BusinessException(
            ErrorCode.JD_CRAWL_FAILED,
            f"Boss 抓取失败（重试 3 次）: {last_err}",
        )

    async def _crawl_once(self, url: str, ua: str) -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            try:
                ctx = await browser.new_context(
                    user_agent=ua,
                    viewport={"width": 1920, "height": 1080},
                    locale="zh-CN",
                )
                page = await ctx.new_page()
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=settings.crawler_timeout_sec * 1000,
                )
                await page.wait_for_timeout(3000)

                # 尝试多个选择器
                for selector in [".job-detail", ".job-sec-text", "body"]:
                    try:
                        await page.wait_for_selector(selector, timeout=5000)
                        text = (await page.inner_text(selector)) or ""
                        if len(text.strip()) > 100:
                            return text
                    except Exception:  # noqa: BLE001
                        continue

                text = (await page.inner_text("body")) or ""
                if len(text.strip()) < 50:
                    raise BusinessException(
                        ErrorCode.CRAWLER_BLOCKED, "Boss 抓取内容过短，可能触发验证码"
                    )
                return text
            finally:
                await browser.close()
