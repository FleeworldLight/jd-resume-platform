"""批量抓取：复用同一个浏览器实例。

单个 URL 的抓取细节（选择器重试、元数据提取）仍由各 strategy 定义；
本模块只负责编排：浏览器复用、UA 轮换、限速、错误隔离。

为什么要单独一个模块：strategy.crawl() 每次都会 launch 一个新浏览器，
批量抓 100 个职位会因此多花数分钟。这里改成全程复用同一 browser/context，
单页只开一个 page。
"""
from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import async_playwright

from app.core.config import settings
from app.core.logging import get_logger
from app.crawler.strategies.boss import BossCrawler
from app.crawler.strategies.nowcoder import NowcoderCrawler, _load_ua_pool
from app.crawler.text_utils import trim_leading_noise

logger = get_logger(__name__)

_STRATEGIES: dict[str, type] = {
    "BOSS": BossCrawler,
    "NOWCODER": NowcoderCrawler,
}

# 各来源详情页的正文选择器；为空表示正文直接取 body
_DETAIL_SELECTORS: dict[str, tuple[str, ...]] = {
    "BOSS": (".job-detail", ".job-sec-text"),
    "NOWCODER": (),
}

# 页面里出现这些字样，说明被风控或落到了登录页
BLOCK_HINTS = (
    "异常行为", "安全验证", "请先登录", "登录后查看",
    "验证码登录", "扫码登录", "登录/注册",
)

MIN_TEXT_LEN = 50


@dataclass
class FetchResult:
    """单个职位的抓取结果。"""

    url: str
    raw_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and len(self.raw_text.strip()) >= MIN_TEXT_LEN


async def fetch_details(
    source: str,
    urls: list[str],
    *,
    delay: float = 1.5,
    headless: bool = True,
    user_data_dir: str | None = None,
    storage_state: str | None = None,
    timeout_sec: int | None = None,
    on_progress: Callable[[int, int, FetchResult], None] | None = None,
) -> list[FetchResult]:
    """批量抓取职位详情页。

    Args:
        source: "BOSS" / "NOWCODER"
        urls: 详情页 URL 列表
        delay: 两个请求之间的基础间隔（秒），会叠加 0~0.8s 随机抖动
        headless: 是否无头模式
        user_data_dir: 非空时使用持久化上下文（可复用已登录会话）
        on_progress: 每完成一条回调 (已完成数, 总数, 结果)
    """
    strategy = _STRATEGIES[source]()
    selectors = _DETAIL_SELECTORS.get(source, ())
    timeout_ms = (timeout_sec or settings.crawler_timeout_sec) * 1000
    ua_pool = _load_ua_pool()
    results: list[FetchResult] = []

    async with async_playwright() as p:
        if user_data_dir:
            ctx = await p.chromium.launch_persistent_context(
                user_data_dir,
                headless=headless,
                user_agent=random.choice(ua_pool),
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            browser = None
        else:
            browser = await p.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            ctx_kwargs: dict = {
                "user_agent": random.choice(ua_pool),
                "viewport": {"width": 1920, "height": 1080},
                "locale": "zh-CN",
            }
            if storage_state:
                ctx_kwargs["storage_state"] = storage_state
            ctx = await browser.new_context(**ctx_kwargs)

        try:
            for idx, url in enumerate(urls, start=1):
                result = FetchResult(url=url)
                page = None
                try:
                    page = await ctx.new_page()
                    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    await page.wait_for_timeout(2200)

                    text = ""
                    for selector in selectors:
                        try:
                            await page.wait_for_selector(selector, timeout=3500)
                            candidate = (await page.inner_text(selector)) or ""
                            if len(candidate.strip()) > 100:
                                text = candidate
                                break
                        except Exception:  # noqa: BLE001
                            continue
                    if not text:
                        text = (await page.inner_text("body")) or ""

                    if len(text.strip()) < MIN_TEXT_LEN:
                        result.error = "内容过短（可能被风控）"
                    elif any(hint in text[:800] for hint in BLOCK_HINTS):
                        result.error = "被风控拦截（需要登录或换网络）"
                    else:
                        # 元数据从完整文本提取，之后再裁掉前置导航
                        try:
                            result.metadata = await strategy._extract_metadata(page, text)  # noqa: SLF001
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("batch.metadata_failed", url=url, error=str(exc))
                        result.raw_text = trim_leading_noise(
                            text, result.metadata.get("position")
                        )
                        if len(result.raw_text.strip()) < MIN_TEXT_LEN:
                            result.error = "清洗后内容过短"
                        elif not (
                            result.metadata.get("position")
                            or result.metadata.get("company")
                        ):
                            # 兜底：既没职位名也没公司名，基本是登录页 / 模板页 / 空壳页。
                            # 曾把 Boss 的登录页当成职位入库，这里必须拦掉。
                            result.error = "未提取到职位名与公司名（疑似登录页或模板页）"
                except Exception as exc:  # noqa: BLE001
                    result.error = f"{type(exc).__name__}: {str(exc)[:200]}"
                    logger.warning("batch.fetch_failed", url=url, error=result.error)
                finally:
                    if page is not None:
                        try:
                            await page.close()
                        except Exception:  # noqa: BLE001
                            pass

                results.append(result)
                if on_progress:
                    on_progress(idx, len(urls), result)

                # 限速：最后一条之后不再等待
                if idx < len(urls) and delay > 0:
                    await asyncio.sleep(delay + random.random() * 0.8)
        finally:
            try:
                await ctx.close()
            except Exception:  # noqa: BLE001
                pass
            if browser is not None:
                await browser.close()

    return results
