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
from app.crawler.text_utils import clean_lines, trim_leading_noise

logger = get_logger(__name__)

_UA_POOL: list[str] | None = None

# 详情页链接形如 https://www.nowcoder.com/jobs/detail/123456
_DETAIL_MARKER = "/jobs/detail/"

_CITY_KEYWORDS = (
    "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京",
    "西安", "苏州", "长沙", "重庆", "天津", "郑州", "合肥", "全国",
)

_EDUCATION_KEYWORDS = {"不限", "大专", "本科", "硕士", "博士", "学历不限"}

# 公司名在正文里的形态：`北京小桔科技有限公司·校招经理`
_COMPANY_ROLE_RE = re.compile(
    r"^(.{2,40}?)·(招聘|校招|社招|HR|人事|经理|专员|主管|总监|负责人|实习生)"
)


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
                    "els => els.map(a => a.href)"
                    ".filter(h => h && h.indexOf('/jobs/detail/') !== -1)"
                )
                results: list[str] = []
                for href in hrefs:
                    # 去掉 query/fragment，保证同一职位只存一条
                    absolute = urljoin(url, href).split("#", 1)[0].split("?", 1)[0]
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
                # 元数据从完整文本提取，随后再裁掉前置导航
                metadata = await self._extract_metadata(page, text)
                self.metadata = metadata
                return trim_leading_noise(text, metadata.get("position"))
            finally:
                await browser.close()

    async def _extract_metadata(self, page, text: str) -> dict[str, str | int | None]:
        """提取牛客详情页的稳定展示字段，LLM 不可用时也能展示职位。"""
        title = (await page.locator("h1").first.text_content() or "").strip() or None
        lines = clean_lines(text)

        salary = next((line for line in lines if re.search(r"\d+\s*-\s*\d+\s*K", line)), "")
        salary_match = re.search(r"(\d+)\s*-\s*(\d+)\s*K", salary)
        city = next((line for line in lines if line in _CITY_KEYWORDS), None)
        company = await self._extract_company(page, lines, title)
        education = next((line for line in lines if line in _EDUCATION_KEYWORDS), None)
        experience = next(
            (line for line in lines if re.search(r"\d{4}届|经验不限|应届", line)), None
        )
        return {
            "position": title,
            "company": company,
            "salary_min": int(salary_match.group(1)) if salary_match else None,
            "salary_max": int(salary_match.group(2)) if salary_match else None,
            "city": city,
            "education": education,
            "experience": experience,
        }

    async def _extract_company(self, page, lines: list[str], title: str | None) -> str | None:
        """公司名有三处线索，按可靠度依次尝试。

        注意优先级：DOM 里的 `[class*="company"]` 区块混有「查看其他 N 个职位」
        等噪声，可靠度反而低于正文，因此放在后面。
        """
        # 1) 正文：公司行紧邻「反馈率」上一行，形如「北京小桔科技有限公司·校招经理」
        for idx, line in enumerate(lines):
            if line.startswith("反馈率") and idx > 0:
                head = lines[idx - 1].split("·", 1)[0].strip()
                if 1 < len(head) <= 40:
                    return head

        # 2) 正文兜底：含「·招聘/·校招/·HR」等角色后缀的行
        for line in lines:
            match = _COMPANY_ROLE_RE.match(line)
            if match:
                return match.group(1).strip()

        # 3) DOM：公司区块的首个词（形如「滴滴 工具 不需要融资 … 查看其他 8 个职位」）
        try:
            block = (await page.locator('[class*="company"]').first.text_content() or "").strip()
            token = block.split()[0] if block.split() else ""
            if 1 < len(token) <= 30 and "查看" not in token and "职位" not in token:
                return token
        except Exception:  # noqa: BLE001
            pass

        # 4) 页面 title 形如「职位_公司校招_牛客网」
        if title:
            try:
                page_title = await page.title()
                segments = page_title.split("_")
                if len(segments) >= 2:
                    candidate = re.sub(r"(校招|社招|招聘)$", "", segments[1]).strip()
                    if 1 < len(candidate) <= 30:
                        return candidate
            except Exception:  # noqa: BLE001
                pass
        return None
