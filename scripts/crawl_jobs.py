#!/usr/bin/env python
"""批量抓取岗位 JD 并写入 SQLite。

用法（在仓库根目录执行）：

    backend\\.venv\\Scripts\\python.exe scripts\\crawl_jobs.py --limit 100

    # 只抓牛客
    ... --source nowcoder --limit 100

    # 只抓 Boss
    ... --source boss --query Python --city 100010000 --limit 50

    # 牛客改走 DOM 抓取（默认走官方接口）
    ... --source nowcoder --nowcoder-mode dom --limit 20

    # 牛客全量（分类 + 关键词 + 多端点，去重后 3000+ 条）
    ... --source nowcoder --nowcoder-scope full --limit 5000 --yes

    # 先只看会发现什么，不入库
    ... --dry-run --limit 20

数据落库
--------
* 写入 `backend/data/jd_platform.db` 的 `jds` 表，按 `source_url` 去重
  （比较前会去掉 query/fragment，避免同一职位重复入库）。
* 默认只保存「原文 + 规则/接口字段」，crawl_status=PARSED。
  加 `--structure` 才再跑一次 LLM 结构化（默认 mock provider 离线可用）。
* 接口路径会把 `edu_level` 等原始码放进 `structured.crawl_meta`，便于回溯。
  注意：如果之后开启 `--structure`，LLM 结果会覆盖这个字段。

合规提醒
--------
* 牛客走的是它自己前端调用的公开接口；Boss 走 DOM 抓取。
* 请遵守目标站点 robots 与服务条款，仅用于个人求职分析。
* 默认已限速（牛客接口 0.8s / Boss 每页 1.5s+抖动），请勿设为 0 压站。
"""
from __future__ import annotations

import argparse
import asyncio
import math
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

# 必须先切换工作目录：settings 读 .env、DATABASE_URL 的相对路径
# 都是相对「进程工作目录」解析的。
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

try:  # Windows 控制台中文输出
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass

from sqlalchemy import func, select  # noqa: E402

from app.crawler.batch import FetchResult, fetch_details  # noqa: E402
from app.crawler.nowcoder_api import (  # noqa: E402
    KEYWORD_SEEDS,
    RECRUIT_TYPES_DISTINCT,
    NowcoderApiClient,
    NowcoderJob,
)
from app.crawler.strategies.boss import BossCrawler  # noqa: E402
from app.crawler.strategies.nowcoder import NowcoderCrawler  # noqa: E402
from app.db.init_db import init_db  # noqa: E402
from app.db.models.jd import Jd  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402

DEFAULT_NOWCODER_LISTING = "https://www.nowcoder.com/jobs/school/jobs"
# Boss 城市码：101010100=全国, 100010000=北京, 101020100=上海, 101280600=深圳
DEFAULT_BOSS_CITY = "100010000"

SAFE_LIMIT = 300  # 超过这个数量必须显式加 --yes


def canonical_url(url: str) -> str:
    """去掉 query / fragment / 结尾斜杠，用于去重比对。"""
    return url.split("#", 1)[0].split("?", 1)[0].rstrip("/")


def build_boss_search_url(query: str, city: str, page: int = 1) -> str:
    from urllib.parse import quote

    return (
        "https://www.zhipin.com/web/geek/job"
        f"?query={quote(query)}&city={city}&page={page}"
    )


# ---------------- 牛客：接口路径 ----------------
def jobs_to_results(jobs: list[NowcoderJob]) -> list[FetchResult]:
    return [
        FetchResult(url=job.url, raw_text=job.raw_text, metadata=job.to_metadata())
        for job in jobs
    ]


# 牛客的招聘类型。**实测只有 0/1/2/3 返回不同数据**，
# 4 及以上（含 4~30）都会回落到与 1 相同的 200 条 → 扫了纯属浪费时间。
ALL_RECRUIT_TYPES = RECRUIT_TYPES_DISTINCT


def parse_recruit_types(raw: str) -> list[int]:
    """解析 --nowcoder-recruit-type：支持 '1'、'1,2,4'、'all'。"""
    value = (raw or "").strip().lower()
    if value in ("all", "*", ""):
        return list(ALL_RECRUIT_TYPES) if value else [1]
    types: list[int] = []
    for piece in value.split(","):
        piece = piece.strip()
        if piece:
            types.append(int(piece))
    return types or [1]


async def collect_nowcoder_api(args: argparse.Namespace, want: int) -> list[NowcoderJob]:
    """牛客接口抓取。

    scope=school：只按 recruitType 分类取（0/1/2/3，约 450 条）
    scope=full  ：再叠加关键词检索与其它列表端点，能拿到 3000+ 条（仍是去重后）
    """
    client = NowcoderApiClient()

    if getattr(args, "nowcoder_scope", "school") == "full":
        print("\n[NOWCODER] 全量扫描：分类 × 关键词 × 多端点，按 job_id 去重合并")
        print(f"[NOWCODER] 关键词种子 {len(KEYWORD_SEEDS)} 个，预计 200+ 次低频请求\n")

        def on_progress(phase: str, label: str, total: int) -> None:
            print(f"[NOWCODER] [{phase}] {label} → 累计唯一 {total}", flush=True)

        jobs = await client.fetch_all(limit=want if want > 0 else 10**6, on_progress=on_progress)
        print(f"\n[NOWCODER] 全量扫描结束，去重后共 {len(jobs)} 条职位")
        return jobs[:want] if want > 0 else jobs

    types = parse_recruit_types(args.nowcoder_recruit_type)
    mode_desc = "多类型合并去重" if len(types) > 1 else "单类型"
    print(f"\n[NOWCODER] 走官方接口抓取 · {mode_desc} · recruitType={types}")

    merged: dict[int, NowcoderJob] = {}
    for rt in types:
        def on_page(page: int, got: int, total: Any = None, total_page: Any = None,
                    _rt: int = rt) -> None:
            print(f"[NOWCODER] recruitType={_rt} 第 {page} 页完成"
                  f"（本页累计 {got} / 站点 {total} 条，{total_page} 页）")

        try:
            jobs = await client.fetch_jobs(
                limit=want if want > 0 else 10**6,
                recruit_type=rt,
                on_page=on_page,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[NOWCODER] recruitType={rt} 抓取失败: {type(exc).__name__}: {exc}")
            continue

        added = 0
        for job in jobs:
            if job.job_id not in merged:
                merged[job.job_id] = job
                added += 1
        print(f"[NOWCODER] recruitType={rt} 返回 {len(jobs)} 条，新增 {added} 条"
              f"（累计唯一 {len(merged)}）")
        if want > 0 and len(merged) >= want:
            print(f"[NOWCODER] 已达目标 {want} 条，停止继续取类型")
            break

        # 类型之间稍作停顿，保持低频（整个全量通常也就十几次请求）
        await asyncio.sleep(1.0)

    result = list(merged.values())
    if want > 0:
        result = result[:want]
    print(f"[NOWCODER] 合并去重后共 {len(result)} 条职位")
    return result


# ---------------- 牛客 / Boss：DOM 路径 ----------------
async def collect_urls(args: argparse.Namespace, source: str, want: int) -> list[str]:
    """取某个来源的职位详情链接。失败时返回空列表并打印原因。"""
    print(f"\n[{source}] 正在获取职位列表…")
    urls: list[str] = []
    for page in range(1, 6):
        try:
            if source == "NOWCODER":
                listing = args.nowcoder_url if page == 1 else f"{args.nowcoder_url}?page={page}"
                got = await NowcoderCrawler().list_job_urls(listing, limit=30)
            else:
                got = await BossCrawler().list_job_urls(
                    build_boss_search_url(args.query, args.city, page),
                    limit=30,
                    storage_state=args.storage_state,
                )
        except Exception as exc:  # noqa: BLE001
            print(f"[{source}] 第 {page} 页失败: {exc}")
            break
        fresh = [u for u in got if u not in urls]
        urls.extend(fresh)
        print(f"[{source}] 第 {page} 页 +{len(fresh)} 条（累计 {len(urls)}）")
        if len(urls) >= want or not fresh:
            break
    return urls[:want]


# ---------------- 落库 ----------------
async def save_results(
    source: str,
    results: list[FetchResult],
    structure: bool,
    crawl_meta: dict[str, dict] | None = None,
    overwrite: bool | None = None,
) -> dict[str, int]:
    """写入 SQLite，按规范化 source_url 去重。

    overwrite 为 None 时按「是否传入 crawl_meta」推断：
    接口路径字段权威（「薪资面议」会解析成 None，必须覆盖写，否则会留下
    上一轮的假数据），DOM 路径只在有新值时更新，避免抹掉已有字段。
    """
    stat = {"inserted": 0, "updated": 0, "skipped": 0}
    crawl_meta = crawl_meta or {}
    if overwrite is None:
        overwrite = bool(crawl_meta)

    async with SessionLocal() as db:
        for res in results:
            if not res.ok:
                stat["skipped"] += 1
                continue

            canon = canonical_url(res.url)
            existing = (
                await db.execute(select(Jd).where(Jd.source_url == canon).limit(1))
            ).scalar_one_or_none()
            if existing is None:
                existing = (
                    await db.execute(
                        select(Jd).where(Jd.source_url.like(canon + "%")).limit(1)
                    )
                ).scalar_one_or_none()

            if existing is None:
                jd = Jd(source=source, source_url=canon, raw_text=res.raw_text)
                db.add(jd)
                stat["inserted"] += 1
            else:
                jd = existing
                jd.source_url = canon
                jd.raw_text = res.raw_text
                stat["updated"] += 1

            for field_name in (
                "company", "position", "salary_min", "salary_max",
                "city", "education", "experience",
            ):
                value = res.metadata.get(field_name)
                if value is not None or overwrite:
                    setattr(jd, field_name, value)
            jd.crawl_status = "PARSED"
            jd.crawl_error = None

            meta = crawl_meta.get(canon)
            if meta:
                jd.structured = {"crawl_meta": meta}

        await db.commit()

    if structure:
        await structure_all(results)

    return stat


async def structure_all(results: list[FetchResult]) -> None:
    from app.services.jd_service import JdService
    from app.services.llm_service import LLMService

    ok_urls = [canonical_url(r.url) for r in results if r.ok]
    if not ok_urls:
        return
    async with SessionLocal() as db:
        service = JdService(db, LLMService(db))
        for idx, url in enumerate(ok_urls, start=1):
            jd = (
                await db.execute(select(Jd).where(Jd.source_url == url))
            ).scalar_one_or_none()
            if jd is None:
                continue
            print(f"  结构化 {idx}/{len(ok_urls)} jd_id={jd.id}", end="\r", flush=True)
            try:
                await service.structure_jd(jd.id)
            except Exception as exc:  # noqa: BLE001
                print(f"\n  结构化失败 jd_id={jd.id}: {exc}")
        print()


# ---------------- 主流程 ----------------
async def main() -> int:
    parser = argparse.ArgumentParser(
        description="批量抓取岗位 JD 写入 SQLite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--source", choices=["nowcoder", "boss", "all"], default="all")
    parser.add_argument("--limit", type=int, default=100, help="本次抓取的目标总条数")
    parser.add_argument("--per-source-limit", type=int, default=None, help="每个来源各抓这么多")
    parser.add_argument("--nowcoder-mode", choices=["api", "dom"], default="api",
                        help="牛客抓取方式：api=官方接口（默认、快），dom=逐页渲染抓取")
    parser.add_argument("--nowcoder-recruit-type", default="1",
                        help="牛客招聘类型：数字、逗号分隔（如 1,2）、或 all（0/1/2/3 合并去重）")
    parser.add_argument("--nowcoder-scope", choices=["school", "full"], default="school",
                        help="牛客抓取范围：school=按分类（约 450 条）；full=分类+关键词+多端点（3000+ 条）")
    parser.add_argument("--nowcoder-url", default=DEFAULT_NOWCODER_LISTING)
    parser.add_argument("--query", default="Python", help="Boss 搜索关键词")
    parser.add_argument("--city", default=DEFAULT_BOSS_CITY, help="Boss 城市码，默认北京")
    parser.add_argument("--delay", type=float, default=1.5, help="Boss DOM 抓取的请求间隔（秒）")
    parser.add_argument("--timeout", type=int, default=30, help="单页超时（秒）")
    parser.add_argument("--headless", dest="headless", action="store_true", default=True)
    parser.add_argument("--no-headless", dest="headless", action="store_false")
    parser.add_argument("--user-data-dir", default=None, help="持久化浏览器目录（可复用登录态）")
    parser.add_argument("--storage-state", default=None,
                        help="已登录会话文件（scripts/boss_login.py 生成），Boss 必需")
    parser.add_argument("--structure", action="store_true", help="抓完后额外跑 LLM 结构化")
    parser.add_argument("--dry-run", action="store_true", help="只取列表，不入库")
    parser.add_argument("--yes", action="store_true", help=f"确认超过 {SAFE_LIMIT} 条的大批量抓取")
    args = parser.parse_args()

    sources = ["NOWCODER", "BOSS"] if args.source == "all" else [args.source.upper()]
    if args.per_source_limit is not None:
        quota = {s: args.per_source_limit for s in sources}
    else:
        per = math.ceil(args.limit / len(sources))
        quota = {s: per for s in sources}
    total_target = sum(quota.values())

    print("=" * 64)
    print("  岗位 JD 批量抓取")
    print("=" * 64)
    print(f"  来源      : {', '.join(sources)}")
    print(f"  目标条数  : {total_target}   " + "  ".join(f"{k}={v}" for k, v in quota.items()))
    print(f"  牛客模式  : {args.nowcoder_mode}")
    print(f"  写入位置  : {BACKEND / 'data' / 'jd_platform.db'}")
    print(f"  结构化    : {'开' if args.structure else '关（只存原文+字段）'}")
    print("-" * 64)
    print("  提示：请遵守目标站点 robots 与服务条款，仅用于个人求职分析，")
    print("        不要设置 --delay 0，不要高频重复抓取。")
    print("=" * 64)

    if total_target > SAFE_LIMIT and not args.yes:
        print(f"\n目标 {total_target} 条超过安全阈值 {SAFE_LIMIT}，请确认后加 --yes 再执行。")
        return 2

    await init_db()

    grand = {"inserted": 0, "updated": 0, "skipped": 0}
    summary: list[tuple[str, int, int, int]] = []

    for source in sources:
        want = quota[source]
        results: list[FetchResult] = []
        crawl_meta: dict[str, dict] = {}

        if source == "NOWCODER" and args.nowcoder_mode == "api":
            jobs = await collect_nowcoder_api(args, want)
            results = jobs_to_results(jobs)
            crawl_meta = {canonical_url(j.url): j.extra for j in jobs}
        else:
            urls = await collect_urls(args, source, want)
            if not urls:
                print(f"[{source}] 未取到任何职位链接，跳过。")
                summary.append((source, 0, 0, 0))
                continue
            print(f"[{source}] 待抓详情 {len(urls)} 条…")
            if args.dry_run:
                for u in urls[:10]:
                    print("   ", u)
                if len(urls) > 10:
                    print(f"    … 其余 {len(urls) - 10} 条略")
                continue

            def progress(done: int, total: int, res: FetchResult, _src=source) -> None:
                flag = "OK " if res.ok else "ERR"
                tail = "" if res.ok else f"  <- {res.error}"
                print(f"  [{done:>3}/{total}] {flag} {res.url[:66]}{tail}", flush=True)

            results = await fetch_details(
                source,
                urls,
                delay=args.delay,
                headless=args.headless,
                user_data_dir=args.user_data_dir,
                storage_state=args.storage_state,
                timeout_sec=args.timeout,
                on_progress=progress,
            )

        if args.dry_run:
            print(f"[{source}] dry-run：解析到 {len(results)} 条，未入库。")
            for res in results[:5]:
                md = res.metadata
                print(f"    {md.get('company')} | {md.get('position')} | {md.get('city')} | "
                      f"{md.get('salary_min')}-{md.get('salary_max')}")
            continue

        stat = await save_results(source, results, args.structure, crawl_meta)
        ok = sum(1 for r in results if r.ok)
        print(
            f"[{source}] 完成：成功 {ok}/{len(results)}｜入库新增 {stat['inserted']}、"
            f"更新 {stat['updated']}、跳过 {stat['skipped']}"
        )
        summary.append((source, ok, stat["inserted"], stat["updated"]))
        for key in grand:
            grand[key] += stat[key]

    if not args.dry_run:
        await print_summary(summary, grand)

    await engine.dispose()
    return 0


async def print_summary(summary: list[tuple[str, int, int, int]], grand: dict[str, int]) -> None:
    async with SessionLocal() as db:
        total_rows = (await db.execute(select(func.count(Jd.id)))).scalar_one()
        by_source = (
            await db.execute(select(Jd.source, func.count(Jd.id)).group_by(Jd.source))
        ).all()
        rows = (
            await db.execute(select(Jd).order_by(Jd.id.desc()).limit(10))
        ).scalars().all()

    print("\n" + "=" * 64)
    print("  汇总")
    print("=" * 64)
    for source, ok, ins, upd in summary:
        print(f"  {source:<10} 抓取成功 {ok:>4}｜新增 {ins:>4}｜更新 {upd:>4}")
    print(f"  本次合计  新增 {grand['inserted']}｜更新 {grand['updated']}｜跳过 {grand['skipped']}")
    print(f"  jds 表现有总行数: {total_rows}")
    for src, cnt in by_source:
        print(f"    - {src}: {cnt}")

    print("\n  最近入库预览：")
    for r in rows:
        salary = (
            f"{r.salary_min}-{r.salary_max}K"
            if r.salary_min is not None and r.salary_max is not None
            else "-"
        )
        print(f"    #{r.id:<4} [{(r.source or '?'):<8}] {(r.company or '?')[:16]:<18} "
              f"{(r.position or '?')[:24]:<26} {(r.city or '-'):<6} {salary}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
