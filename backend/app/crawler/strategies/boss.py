"""Boss 直聘（zhipin/boss）JD 爬虫。

设计文档 §9.4：UA 池轮换 + 失败指数退避。
Boss 经常要验证码，先等几秒并尝试多个选择器。

风控说明：Boss 对数据中心 / 代理 IP 风控较严，列表接口可能直接返回
    {"code":35,"message":"您的IP地址存在异常行为."}
此时请改用家用宽带，或通过 `--user-data-dir` 复用已登录的浏览器会话。
本文件中的 `list_job_urls` / `_extract_metadata` 与 nowcoder.py 同构，
但在受风控的 IP 环境下无法完成端到端验证。
"""
from __future__ import annotations

import random
import re
import time
from urllib.parse import urljoin

from playwright.async_api import async_playwright

from app.core.config import settings
from app.core.exceptions import BusinessException, ErrorCode
from app.core.logging import get_logger
from app.crawler.strategies.nowcoder import _load_ua_pool

logger = get_logger(__name__)

# Boss 详情页链接形如 https://www.zhipin.com/job_detail/xxxxxxxx.html
_DETAIL_MARKER = "/job_detail/"

_CITY_KEYWORDS = (
    "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京",
    "西安", "苏州", "长沙", "重庆", "天津", "郑州", "合肥", "全国",
)

# 列表页出现这些字样基本可判定被风控 / 要求登录
_BLOCK_HINTS = ("异常行为", "安全验证", "请先登录", "登录后查看", "验证码")


class BossCrawler:
    name = "boss"

    def __init__(self) -> None:
        self.metadata: dict[str, str | int | None] = {}

    # ---------- 列表页：提取职位详情链接 ----------
    async def list_job_urls(
        self, url: str, limit: int = 10, storage_state: str | None = None
    ) -> list[str]:
        """从 Boss 搜索页提取职位详情链接。

        Args:
            storage_state: 已登录会话文件（由 `scripts/boss_login.py` 生成）。
                Boss 对未登录访问统一返回 code 35「IP 地址存在异常行为」，
                必须带上真实登录会话才可能拿到数据。
        """
        ua = random.choice(_load_ua_pool())
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            try:
                ctx_kwargs: dict = {
                    "user_agent": ua,
                    "viewport": {"width": 1920, "height": 1080},
                    "locale": "zh-CN",
                }
                if storage_state:
                    ctx_kwargs["storage_state"] = storage_state
                ctx = await browser.new_context(**ctx_kwargs)
                page = await ctx.new_page()
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=settings.crawler_timeout_sec * 1000,
                )
                await page.wait_for_timeout(5000)

                body = (await page.inner_text("body")) or ""
                if len(body.strip()) < 50 or any(h in body for h in _BLOCK_HINTS):
                    raise BusinessException(
                        ErrorCode.CRAWLER_BLOCKED,
                        "Boss 列表页被风控拦截（IP 异常或未登录）。"
                        "可先运行 scripts/boss_login.py 准备登录态，再用 --storage-state 复用。",
                    )

                hrefs = await page.locator("a").evaluate_all(
                    "els => els.map(a => a.href)"
                    ".filter(h => h && h.indexOf('/job_detail/') !== -1)"
                )
                # 必须是 /job_detail/<职位ID>.html。
                # 搜索页模板里还存在一个不带 ID 的空链接 /job_detail/，
                # 它会把登录页当成职位抓回来（已实测踩坑），必须排除。
                detail_re = re.compile(r"/job_detail/[0-9A-Za-z_~\-]{6,}\.html")
                skipped = 0
                results: list[str] = []
                for href in hrefs:
                    absolute = urljoin(url, href).split("?", 1)[0]
                    if not detail_re.search(absolute):
                        skipped += 1
                        continue
                    if absolute not in results:
                        results.append(absolute)
                    if len(results) >= max(1, min(limit, 60)):
                        break
                if skipped:
                    logger.warning("crawler.boss.skipped_invalid_links", count=skipped)
                if not results:
                    raise BusinessException(
                        ErrorCode.JD_CRAWL_FAILED,
                        f"Boss 搜索页未发现职位详情链接（页面正文 {len(body.strip())} 字）。"
                        "通常说明未登录或该网络出口被风控 —— 请先运行 "
                        "scripts/boss_login.py 准备登录态，再用 --storage-state 复用。",
                    )
                return results
            finally:
                await browser.close()

    # ---------- 详情页：抓取原文 ----------
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
                text = ""
                for selector in [".job-detail", ".job-sec-text", "body"]:
                    try:
                        await page.wait_for_selector(selector, timeout=5000)
                        candidate = (await page.inner_text(selector)) or ""
                        if len(candidate.strip()) > 100:
                            text = candidate
                            break
                    except Exception:  # noqa: BLE001
                        continue

                if not text:
                    text = (await page.inner_text("body")) or ""
                if len(text.strip()) < 50:
                    raise BusinessException(
                        ErrorCode.CRAWLER_BLOCKED, "Boss 抓取内容过短，可能触发验证码"
                    )
                if any(h in text[:500] for h in _BLOCK_HINTS):
                    raise BusinessException(
                        ErrorCode.CRAWLER_BLOCKED, "Boss 详情页被风控拦截"
                    )

                from app.crawler.text_utils import trim_leading_noise

                metadata = await self._extract_metadata(page, text)
                self.metadata = metadata
                return trim_leading_noise(text, metadata.get("position"))
            finally:
                await browser.close()

    # ---------- 详情页：规则提取结构化字段 ----------
    async def _extract_metadata(self, page, text: str) -> dict[str, str | int | None]:
        """提取 Boss 详情页的稳定展示字段，LLM 不可用时也能展示职位。"""
        title = None
        for selector in (".job-primary .name h1", ".name h1", "h1"):
            try:
                candidate = (await page.locator(selector).first.text_content()) or ""
                if candidate.strip():
                    title = candidate.strip()
                    break
            except Exception:  # noqa: BLE001
                continue

        salary_text = ""
        for selector in (".job-primary .salary", ".salary"):
            try:
                candidate = (await page.locator(selector).first.text_content()) or ""
                if candidate.strip():
                    salary_text = candidate.strip()
                    break
            except Exception:  # noqa: BLE001
                continue

        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # 薪资兜底：从正文里找 "15-25K" / "15-25K·14薪"
        if not salary_text:
            salary_text = next(
                (line for line in lines if re.search(r"\d+\s*-\s*\d+\s*K", line)), ""
            )
        salary_match = re.search(r"(\d+)\s*-\s*(\d+)\s*K", salary_text)

        # 城市 / 经验 / 学历：Boss 详情页通常在同一行，如 "北京·朝阳区 3-5年 本科"
        city = next((c for c in _CITY_KEYWORDS if c in text), None)
        experience = next(
            (
                line
                for line in lines
                if re.search(r"(\d+-\d+年|经验不限|应届|在校)", line)
            ),
            None,
        )
        education = next(
            (
                line
                for line in lines
                if line in {"本科", "硕士", "博士", "大专", "学历不限", "中专/中技"}
            ),
            None,
        )

        company = None
        for selector in (".company-info .name", ".sider-company .name", ".company-info h3"):
            try:
                candidate = (await page.locator(selector).first.text_content()) or ""
                if candidate.strip():
                    company = candidate.strip()
                    break
            except Exception:  # noqa: BLE001
                continue
        if not company:
            company = next((line.split("·", 1)[0].strip() for line in lines if "·招聘" in line), None)

        return {
            "position": title,
            "company": company,
            "salary_min": int(salary_match.group(1)) if salary_match else None,
            "salary_max": int(salary_match.group(2)) if salary_match else None,
            "city": city,
            "education": education,
            "experience": experience,
        }
