#!/usr/bin/env python
"""合并 `jds` 表里规范化 URL 相同的重复行。

背景：早期 DOM 抓取把带 query 参数的详情页 URL 存了进去
（`.../jobs/detail/460167?pageSource=5`），而接口抓取存的是规范化 URL
（`.../jobs/detail/460167`），两者指向同一职位却各占一行。
`crawl_jobs.py` 已经在新数据落库时做规范化去重，本脚本用于清理历史存量。

用法（在仓库根目录执行）：

    # 只预览，不动数据（默认）
    backend\\.venv\\Scripts\\python.exe scripts\\dedupe_jds.py

    # 确认后真正执行删除
    backend\\.venv\\Scripts\\python.exe scripts\\dedupe_jds.py --apply

保留规则：每组保留「信息最全」的一条，优先级依次为
    1. 有 structured.crawl_meta（接口抓取，字段最权威）
    2. 已填充字段更多（company / position / city / salary_min / education / experience）
    3. raw_text 更长
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass

from sqlalchemy import func, select  # noqa: E402

from app.db.models.jd import Jd  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402

_FIELDS = ("company", "position", "city", "salary_min", "education", "experience")


def canonical_url(url: str) -> str:
    """去掉 query / fragment / 结尾斜杠。"""
    return url.split("#", 1)[0].split("?", 1)[0].rstrip("/")


def score(jd: Jd) -> tuple[int, int, int]:
    has_meta = 1 if (jd.structured and "crawl_meta" in jd.structured) else 0
    filled = sum(1 for f in _FIELDS if getattr(jd, f) is not None)
    return has_meta, filled, len(jd.raw_text or "")


async def main() -> int:
    parser = argparse.ArgumentParser(description="合并 jds 表中 URL 规范化后重复的行")
    parser.add_argument("--apply", action="store_true", help="真正执行删除（默认只预览）")
    args = parser.parse_args()

    async with SessionLocal() as db:
        total = (await db.execute(select(func.count(Jd.id)))).scalar_one()
        rows = (await db.execute(select(Jd).order_by(Jd.id))).scalars().all()

        groups: dict[str, list[Jd]] = {}
        for jd in rows:
            if jd.source_url:
                groups.setdefault(canonical_url(jd.source_url), []).append(jd)

        dup_groups = {k: v for k, v in groups.items() if len(v) > 1}

        print("=" * 66)
        print(f"  jds 总行数: {total}    唯一规范化 URL: {len(groups)}    重复组: {len(dup_groups)}")
        print("=" * 66)

        to_delete: list[Jd] = []
        for canon, group in sorted(dup_groups.items(), key=lambda kv: -len(kv[1])):
            group.sort(key=score, reverse=True)
            keeper = group[0]
            print(f"\n  {canon}")
            print(f"    保留 #{keeper.id}  {str(keeper.company or '?')[:20]} | "
                  f"{str(keeper.position or '?')[:26]} | 字段 {score(keeper)[1]}/6 | "
                  f"len {len(keeper.raw_text or '')}")
            for extra in group[1:]:
                to_delete.append(extra)
                print(f"    删除 #{extra.id}  {str(extra.company or '?')[:20]} | "
                      f"{str(extra.position or '?')[:26]} | 字段 {score(extra)[1]}/6 | "
                      f"len {len(extra.raw_text or '')}")

        # 顺手把单行但 URL 未规范化的记录改名，避免下次再判重
        renamed = 0
        for canon, group in groups.items():
            if len(group) == 1 and group[0].source_url != canon:
                group[0].source_url = canon
                renamed += 1

        print("\n" + "-" * 66)
        print(f"  待删除重复行: {len(to_delete)}")
        print(f"  待规范化 URL: {renamed}")

        if not args.apply:
            print("\n  这是预览模式，未改动任何数据。确认后加 --apply 执行。")
            await engine.dispose()
            return 0

        for jd in to_delete:
            await db.delete(jd)
        await db.commit()
        remaining = (await db.execute(select(func.count(Jd.id)))).scalar_one()
        print(f"\n  已删除 {len(to_delete)} 行，jds 现有 {remaining} 行。")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
