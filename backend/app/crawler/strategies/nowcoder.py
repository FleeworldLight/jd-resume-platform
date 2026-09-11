"""牛客（nowcoder）JD 爬虫。

设计文档 §9.4：UA 池轮换 + 失败指数退避 + 单 IP 限流。
"""
from __future__ import annotations

import random
import re
import time
from pathlib import Path
from urllib.parse import urljoin

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

    def __init__(self) -> None:
        self.metadata: dict[str, str | int | None] = {}

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

    async def list_job_urls(self, url: str, limit: int = 10) -> list[str]:
        """从牛客校招列表页提取公开职位详情链接。"""
        ua = random.choice(_load_ua_pool())
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
                await page.goto(url, wait_until="domcontentloaded", timeout=settings.crawler_timeout_sec * 1000)
                await page.wait_for_timeout(4000)
                hrefs = await page.locator("a").evaluate_all(
                    "els => els.map(a => a.href).filter(h => /nowcoder\\.com\\/jobs\\/detail\\//.test(h))"
                )
                results: list[str] = []
                for href in hrefs:
                    absolute = urljoin(url, href).split("#", 1)[0]
                    if absolute not in results:
                        results.append(absolute)
                    if len(results) >= max(1, min(limit, 30)):
                        break
                if not results:
                    raise BusinessException(ErrorCode.JD_CRAWL_FAILED, "牛客校招列表未发现职位详情链接")
                return results
            finally:
                await browser.close()

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
                self.metadata = await self._extract_metadata(page, text)
                return text
            finally:
                await browser.close()

    async def _extract_metadata(self, page, text: str) -> dict[str, str | int | None]:
        """提取牛客详情页的稳定展示字段，LLM 不可用时也能展示职位。"""
        title = (await page.locator("h1").first.text_content() or "").strip() or None
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        salary = next((line for line in lines if re.search(r"\d+\s*-\s*\d+K", line)), "")
        salary_match = re.search(r"(\d+)\s*-\s*(\d+)K", salary)
        city = next((line for line in lines if line in {"北京", "上海", "广州", "深圳", "成都", "杭州", "武汉", "西安", "南京", "全国"}), None)
        company = None
        for line in lines:
            if "·招聘" in line:
                company = line.split("·", 1)[0].strip() or None
                break
        education = next((line for line in lines if line in {"本科", "硕士", "博士", "大专", "学历不限"}), None)
        experience = next((line for line in lines if re.search(r"\d{4}届|经验不限", line)), None)
        return {
            "position": title,
            "company": company,
            "salary_min": int(salary_match.group(1)) if salary_match else None,
            "salary_max": int(salary_match.group(2)) if salary_match else None,
            "city": city,
            "education": education,
            "experience": experience,
        }
