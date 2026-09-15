#!/usr/bin/env python
"""导出「静态演示数据」-> frontend/public/demo-data/*.json

背景
----
GitHub Pages 只能托管静态文件，跑不了 FastAPI。于是把后端数据预导出成 JSON，
前端增加一层「离线数据源」（frontend/src/demoData.ts）读这些文件，
使 Pages 上也能看到完整界面：岗位列表可筛选/分页、简历可看、定制化报告可看。

做法
----
不手写字段映射，而是**用进程内的 ASGI 客户端调用真实接口**再落盘，
这样导出的结构与线上接口逐字段一致，前端不用为演示写第二套类型。

用法
----
    backend\\.venv\\Scripts\\python.exe scripts\\export_static_demo.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
OUT_DIR = ROOT / "frontend" / "public" / "demo-data"

# 列表里 raw_text 截断长度：4825 条全带完整正文会让首屏 JSON 到 ~10MB
RAW_TEXT_LIMIT = 300
RAW_TEXT_NOTE = "\n\n……（演示数据仅保留 JD 前 300 字，完整数据请克隆仓库本地运行）"

os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass


def canonical_url(url: str | None) -> str | None:
    """去掉 query/fragment，避免把爬虫追踪参数带进公开数据。"""
    if not url:
        return None
    return url.split("#", 1)[0].split("?", 1)[0].rstrip("/") or None


# UI 实际只从 structured 里读这几项（薪资单位/展示文本/生成方式），
# 其余是抓取溯源信息，公开演示用不到 —— 去掉可省约 0.7MB
STRUCTURED_KEEP = ("salary_month", "salary_display", "salary_unit", "via")


def truncate_raw(item: dict) -> None:
    text = item.get("raw_text") or ""
    if len(text) > RAW_TEXT_LIMIT:
        item["raw_text"] = text[:RAW_TEXT_LIMIT] + RAW_TEXT_NOTE
    item["source_url"] = canonical_url(item.get("source_url"))

    structured = item.get("structured")
    if isinstance(structured, dict):
        meta = structured.get("crawl_meta")
        slim: dict = {}
        if isinstance(meta, dict):
            kept = {k: v for k, v in meta.items() if k in STRUCTURED_KEEP and v is not None}
            if kept:
                slim["crawl_meta"] = kept
        if structured.get("extract_mode"):
            slim["extract_mode"] = structured["extract_mode"]
        item["structured"] = slim or None


def dump(name: str, payload, *, indent: int | None = None) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=indent),
        encoding="utf-8",
    )
    size = path.stat().st_size
    print(f"  {name:<26} {size / 1024:>8.1f} KB")
    return size


async def main() -> int:
    import httpx

    from app.main import app

    transport = httpx.ASGITransport(app=app)
    total_bytes = 0

    async with httpx.AsyncClient(transport=transport, base_url="http://demo") as c:
        async def get_json(path: str):
            r = await c.get(path)
            if r.status_code != 200:
                raise RuntimeError(f"{path} -> HTTP {r.status_code}")
            payload = r.json()
            if payload.get("code") != 0:
                raise RuntimeError(f"{path} -> code={payload.get('code')} {payload.get('message')}")
            return payload["data"]

        print("=== 导出静态演示数据 ===")

        # 1. 岗位：分页取完（接口 page_size 上限 100）
        jobs: list[dict] = []
        page = 1
        total = None
        while True:
            data = await get_json(f"/api/jds?page={page}&page_size=100&sort=oldest")
            total = data["total"]
            items = data["items"]
            if not items:
                break
            jobs.extend(items)
            print(f"  拉取岗位 第 {page} 页 … 累计 {len(jobs)}/{total}", end="\r")
            if len(jobs) >= total:
                break
            page += 1
        print(f"  拉取岗位完成：{len(jobs)}/{total}                ")
        for j in jobs:
            truncate_raw(j)
        total_bytes += dump("jobs.json", {"items": jobs, "total": len(jobs)})

        # 2. 筛选项（直接用后端算好的，保证下拉计数一致）
        facets = await get_json("/api/jds/facets")
        total_bytes += dump("facets.json", facets)

        # 3. 简历（列表 + 详情）
        r_list = await get_json("/api/resumes?page_size=50")
        r_details = {}
        for item in r_list["items"]:
            r_details[str(item["id"])] = await get_json(f"/api/resumes/{item['id']}")
        total_bytes += dump("resumes.json", {"list": r_list, "details": r_details})

        # 4. 定制化（列表 + 详情）
        c_list = await get_json("/api/customizations?page_size=50")
        c_details = {}
        for item in c_list["items"]:
            c_details[str(item["id"])] = await get_json(f"/api/customizations/{item['id']}")
        total_bytes += dump("customizations.json", {"list": c_list, "details": c_details})

        # 5. 模型 Provider（演示页只读展示）
        providers = await get_json("/api/llm-providers")
        total_bytes += dump("llm-providers.json", providers)

        # 6. 健康检查：强制 demo_mode，让前端横幅与按钮文案走演示分支
        health = await get_json("/health")
        health["demo_mode"] = True
        health["crawler_enabled"] = False
        health["static_demo"] = True
        total_bytes += dump("health.json", health)

        # 7. 元信息
        total_bytes += dump(
            "meta.json",
            {
                "generated_by": "scripts/export_static_demo.py",
                "jobs": len(jobs),
                "resumes": len(r_list["items"]),
                "customizations": len(c_list["items"]),
                "raw_text_limit": RAW_TEXT_LIMIT,
            },
        )

    print()
    print(f"合计 {total_bytes / 1024 / 1024:.2f} MB -> {OUT_DIR}")
    print("提示：GitHub Pages 会 gzip 传输，实际首屏体积约为上面的 1/4 ~ 1/5")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
