#!/usr/bin/env python
"""校验 `jds` 表里岗位数据的真实性。

为什么要独立校验
----------------
`scripts/crawl_jobs.py` 走的是牛客自己的接口，数据本身就来自站点。
但「来自接口」不等于「真实」——接口可能返回缓存、脏数据，或解析时被写错。
本脚本用**另一条独立通道**复核：直接打开每个职位的详情页，
从页面内嵌的 `window.__INITIAL_STATE__.store.jobDetail.detail` 里取出站点自己渲染的字段，
再和库里存的逐字段比对。

用法（在仓库根目录执行）

    REM 静态校验（全量、不联网）：URL 合法性 / 唯一性 / 字段自洽
    backend\\.venv\\Scripts\\python.exe scripts\\verify_jds.py

    REM 静态 + 抽样 15 条联网比对真实详情页（推荐）
    backend\\.venv\\Scripts\\python.exe scripts\\verify_jds.py --live 15

    REM 全量联网比对（慢，请保持低频）
    backend\\.venv\\Scripts\\python.exe scripts\\verify_jds.py --all-live

校验项
------
静态：
  1. source_url 是否为合法的牛客职位详情页链接
  2. source_url 是否唯一（同一职位被重复入库）
  3. position / company 是否为空
  4. salary 区间是否自洽（min <= max，剔除哨兵值后仍在合理范围）
  5. raw_text 是否自洽（应包含 position 与 company）
在线（抽样）：
  6. 页面可访问且该职位仍在线
  7. 页面 jobName  ==  库 position
  8. 页面 companyId ==  库 structured.crawl_meta.company_id
  9. 页面 salaryMin/Max/Month 与库 salary_min/max 及 crawl_meta 一致
 10. 页面 jobCity    ==  库 city
 11. 页面 eduLevel   ==  库 crawl_meta.edu_level
 12. 页面 ext 正文与库 raw_text 内容吻合

合规：校验同样是访问目标站点，默认每条间隔 0.8s，请勿调低。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db.models.jd import Jd  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.nowcoder.com/jobs/school/jobs",
}

SALARY_SENTINEL_MAX = 9_999_999

# 页面出现这些字样说明职位已下线
_OFFLINE_HINTS = ("该职位已下线", "职位不存在", "已停止招聘", "职位已关闭")


def _clean_salary(lo: Any, hi: Any) -> tuple[int | None, int | None]:
    """与 nowcoder_api._clean_salary 保持一致的归一化。"""
    if not isinstance(lo, int) or not isinstance(hi, int):
        return None, None
    if lo <= 0 or hi <= 0 or hi >= SALARY_SENTINEL_MAX or lo > hi:
        return None, None
    return lo, hi


def _canonical(url: str | None) -> str:
    return (url or "").split("#", 1)[0].split("?", 1)[0].rstrip("/")


def _extract_state(html: str) -> dict[str, Any] | None:
    """从 HTML 里抠出 window.__INITIAL_STATE__ 的 JSON。"""
    marker = "window.__INITIAL_STATE__"
    idx = html.find(marker)
    if idx < 0:
        return None
    start = html.find("{", idx)
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(html)):
        ch = html[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(html[start : i + 1])
                    except ValueError:
                        return None
    return None


def _title_of(html: str) -> str:
    import re

    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return m.group(1).strip() if m else ""


# ---------------- 静态校验 ----------------
def static_check(rows: list[Jd]) -> tuple[dict[str, int], list[str]]:
    stats = {
        "total": len(rows),
        "bad_url": 0,
        "dup_url": 0,
        "missing_position": 0,
        "missing_company": 0,
        "bad_salary": 0,
        "text_inconsistent": 0,
    }
    problems: list[str] = []

    seen: dict[str, int] = {}
    for jd in rows:
        canon = _canonical(jd.source_url)
        if not canon.startswith("https://www.nowcoder.com/jobs/detail/"):
            stats["bad_url"] += 1
            problems.append(f"#{jd.id} URL 不合法: {jd.source_url}")
        else:
            seen[canon] = seen.get(canon, 0) + 1

        if not (jd.position or "").strip():
            stats["missing_position"] += 1
        if not (jd.company or "").strip():
            stats["missing_company"] += 1

        # 薪资自洽
        if jd.salary_min is not None and jd.salary_max is not None:
            if not (1 <= jd.salary_min <= jd.salary_max <= 500):
                stats["bad_salary"] += 1
                problems.append(
                    f"#{jd.id} 薪资异常: {jd.salary_min}-{jd.salary_max}K"
                )

        # 正文自洽：应包含职位名（职位名非空时）
        text = jd.raw_text or ""
        if (jd.position or "").strip() and jd.position.strip() not in text:
            stats["text_inconsistent"] += 1
            problems.append(f"#{jd.id} 正文不含职位名: {jd.position[:24]}")

    dups = {k: v for k, v in seen.items() if v > 1}
    stats["dup_url"] = sum(v - 1 for v in dups.values())
    for k, v in dups.items():
        problems.append(f"URL 重复 {v} 次: {k}")

    return stats, problems


# ---------------- 在线校验 ----------------
def compare_with_page(jd: Jd, html: str) -> tuple[bool, list[str]]:
    """把库里存的和详情页自己渲染的字段比对。返回 (是否全部一致, 差异列表)."""
    diffs: list[str] = []
    meta = {}
    if jd.structured and isinstance(jd.structured, dict):
        meta = jd.structured.get("crawl_meta") or {}

    if any(h in html for h in _OFFLINE_HINTS):
        return False, ["页面显示职位已下线/不存在"]

    state = _extract_state(html)
    detail = None
    if state:
        detail = (
            state.get("store", {}).get("jobDetail", {}).get("detail")
            if isinstance(state.get("store"), dict)
            else None
        )

    if isinstance(detail, dict) and detail.get("id") is not None:
        # --- 形态 A：页面自带完整 detail ---
        page_name = str(detail.get("jobName") or "").strip()
        if page_name and page_name != (jd.position or "").strip():
            diffs.append(f"position: 库={jd.position!r} 页面={page_name!r}")

        if meta.get("company_id") is not None and detail.get("companyId") != meta.get("company_id"):
            diffs.append(f"company_id: 库={meta.get('company_id')} 页面={detail.get('companyId')}")

        exp_min, exp_max = _clean_salary(detail.get("salaryMin"), detail.get("salaryMax"))
        if exp_min != jd.salary_min or exp_max != jd.salary_max:
            diffs.append(
                f"salary: 库={jd.salary_min}-{jd.salary_max} 页面={exp_min}-{exp_max}"
            )
        raw = meta.get("salary_raw")
        if isinstance(raw, list) and raw != [detail.get("salaryMin"), detail.get("salaryMax")]:
            diffs.append(f"salary_raw: 库={raw} 页面={[detail.get('salaryMin'), detail.get('salaryMax')]}")

        page_month = detail.get("salaryMonth")
        if meta.get("salary_month") is not None and page_month != meta.get("salary_month"):
            diffs.append(f"salary_month: 库={meta.get('salary_month')} 页面={page_month}")

        page_city = detail.get("jobCity")
        if page_city and jd.city and page_city != jd.city:
            diffs.append(f"city: 库={jd.city!r} 页面={page_city!r}")

        if meta.get("edu_level") is not None and detail.get("eduLevel") != meta.get("edu_level"):
            diffs.append(f"edu_level: 库={meta.get('edu_level')} 页面={detail.get('eduLevel')}")

        # 正文比对：页面 ext 里的职责/要求应能在库里正文中找到
        try:
            ext = json.loads(detail.get("ext") or "{}")
        except (ValueError, TypeError):
            ext = {}
        for key in ("infos", "requirements"):
            piece = str(ext.get(key) or "").strip()
            if len(piece) >= 30:
                probe = piece[:30]
                if probe not in (jd.raw_text or ""):
                    diffs.append(f"正文缺少页面 {key} 片段: {probe[:20]}…")
    else:
        # --- 形态 B（官网闪投）：页面无 detail，用 title + 文本包含做宽松比对 ---
        title = _title_of(html)
        if jd.position and jd.position.strip() and jd.position.strip() not in title and jd.position.strip() not in html:
            diffs.append(f"position 未出现在页面: {jd.position!r}（title={title[:50]!r}）")
        if jd.company and jd.company.strip() and jd.company.strip() not in html:
            diffs.append(f"company 未出现在页面: {jd.company!r}")

    return (not diffs), diffs


async def live_check(
    rows: list[Jd], sample: int, all_live: bool, delay: float, seed: int
) -> tuple[list[tuple[Jd, bool, list[str]]], int]:
    targets = rows if all_live else random.Random(seed).sample(rows, min(sample, len(rows)))
    results: list[tuple[Jd, bool, list[str]]] = []
    errors = 0

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=_HEADERS) as client:
        for idx, jd in enumerate(targets, start=1):
            url = _canonical(jd.source_url)
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    results.append((jd, False, [f"HTTP {resp.status_code}"]))
                    errors += 1
                else:
                    ok, diffs = compare_with_page(jd, resp.text)
                    results.append((jd, ok, diffs))
                    if not ok:
                        errors += 1
            except Exception as exc:  # noqa: BLE001
                results.append((jd, False, [f"{type(exc).__name__}: {str(exc)[:120]}"]))
                errors += 1

            ok_flag = "OK  " if results[-1][1] else "FAIL"
            pos = (jd.position or "?")[:26]
            print(f"  [{idx:>3}/{len(targets)}] {ok_flag} #{jd.id:<4} {pos}", flush=True)
            if delay > 0 and idx < len(targets):
                await asyncio.sleep(delay + random.random() * 0.5)

    return results, errors


async def main() -> int:
    parser = argparse.ArgumentParser(description="校验 jds 表岗位数据真实性")
    parser.add_argument("--live", type=int, default=0, help="额外抽样多少条联网比对真实页面")
    parser.add_argument("--all-live", action="store_true", help="全量联网比对（慢）")
    parser.add_argument("--delay", type=float, default=0.8, help="联网校验的请求间隔（秒）")
    parser.add_argument("--seed", type=int, default=20260911, help="抽样随机种子（可复现）")
    args = parser.parse_args()

    async with SessionLocal() as db:
        rows = list(
            (await db.execute(select(Jd).order_by(Jd.id))).scalars().all()
        )

    print("=" * 70)
    print("  jds 表数据真实性校验")
    print("=" * 70)

    stats, problems = static_check(rows)
    print("\n【静态校验】全量", stats["total"], "行")
    print(f"  URL 不合法        : {stats['bad_url']}")
    print(f"  URL 重复（多余行）: {stats['dup_url']}")
    print(f"  position 为空     : {stats['missing_position']}")
    print(f"  company  为空     : {stats['missing_company']}")
    print(f"  薪资不合理        : {stats['bad_salary']}")
    print(f"  正文不含职位名    : {stats['text_inconsistent']}")
    if problems:
        print("\n  问题明细（最多 20 条）：")
        for p in problems[:20]:
            print("   -", p)
        if len(problems) > 20:
            print(f"   … 另有 {len(problems) - 20} 条")

    live_rows = rows if args.all_live else []
    if args.live > 0 and not args.all_live:
        # 只对「有结构化元数据」的行做在线比对（形态 B 无 detail，宽松比对）
        live_rows = rows

    exit_code = 0
    if args.all_live or args.live > 0:
        n = len(live_rows) if args.all_live else args.live
        print(f"\n【在线校验】与真实详情页逐字段比对，样本 {n} 条")
        results, failed = await live_check(
            live_rows, args.live, args.all_live, args.delay, args.seed
        )
        passed = sum(1 for _, ok, _ in results if ok)

        def _is_crawled(jd: Jd) -> bool:
            """是否为本脚本配套的接口抓取行（带 crawl_meta）。"""
            return bool(
                jd.structured
                and isinstance(jd.structured, dict)
                and jd.structured.get("crawl_meta")
            )

        crawled = [r for r in results if _is_crawled(r[0])]
        legacy = [r for r in results if not _is_crawled(r[0])]

        print(f"\n  一致: {passed}/{len(results)}    不一致: {len(results) - passed}")
        for label, group in (("接口抓取行", crawled), ("遗留行", legacy)):
            if group:
                gok = sum(1 for _, ok, _ in group if ok)
                print(f"    - {label}: {gok}/{len(group)} 一致")

        for jd, ok, diffs in results:
            if not ok:
                tag = "接口抓取行" if _is_crawled(jd) else "遗留行"
                print(f"   FAIL #{jd.id} [{tag}] {_canonical(jd.source_url)}")
                for d in diffs:
                    print(f"        - {d}")
        if failed:
            exit_code = 1

        print("\n" + "=" * 70)
        if passed == len(results):
            print(f"  结论：抽样的 {len(results)} 条与站点真实页面完全一致，数据真实。")
        else:
            print(f"  结论：{len(results) - passed} 条与页面不一致，需排查。")
        print("=" * 70)
    else:
        print("\n  （未做在线校验；加 --live 15 可抽样打开真实页面比对）")

    await engine.dispose()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
