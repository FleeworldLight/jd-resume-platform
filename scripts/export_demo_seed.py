#!/usr/bin/env python
"""导出「脱敏演示种子库」-> backend/seed/demo_seed.db

用途
----
部署到免费平台时磁盘是临时的，重启即清空。仓库里带一份种子库，
app 启动时若发现库文件不存在就复制过去（见 app/db/init_db.py），
访客打开就能看到完整的 4800+ 条岗位数据。

做法
----
1. `VACUUM INTO` 整库复制（比逐表导字段靠谱得多）
2. 在副本里做减法：清空 source_url 追踪参数、只保留虚构简历、
   只保留 mock provider、删掉运行期日志
3. `PRAGMA secure_delete=ON` + `VACUUM` 清掉空闲页残留
4. **PII 闸门**：扫描姓名/手机/邮箱/GitHub/学校，命中即报错退出、不产出种子库

用法
----
    backend\\.venv\\Scripts\\python.exe scripts\\export_demo_seed.py
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DB = ROOT / "backend" / "data" / "jd_platform.db"
SEED_DIR = ROOT / "backend" / "seed"
SEED_DB = SEED_DIR / "demo_seed.db"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass

# 这些字符串绝不能出现在公开仓库里（PII 闸门）
FORBIDDEN = [
    "黄锦强",
    "13433883463",
    "2039679110",
    "FleeworldLight",   # GitHub 用户名（仓库地址本身会用，但不该出现在简历数据里）
    "广州南方学院",
]


def walk_strings(node, path=""):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from walk_strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_strings(v, f"{path}[{i}]")


def scan_pii(db_path: Path) -> list[str]:
    """JSON 感知的 PII 扫描：字面 + 解析后再遍历。

    必须两步都做——SQLAlchemy 的 JSON 列会把中文存成 \\uXXXX 转义，
    只做字面匹配会假阴性（这个坑踩过）。
    """
    hits: list[str] = []
    c = sqlite3.connect(str(db_path))
    try:
        tables = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
        for t in tables:
            cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
            for col in cols:
                try:
                    rows = c.execute(
                        f"select rowid, {col} from {t} where {col} is not null"
                    ).fetchall()
                except Exception:  # noqa: BLE001
                    continue
                for rid, val in rows:
                    if not isinstance(val, str):
                        continue
                    for kw in FORBIDDEN:
                        if kw in val:
                            hits.append(f"{t}.{col} rowid={rid} 字面命中 {kw}")
                    s = val.strip()
                    if s[:1] in "{[":
                        try:
                            parsed = json.loads(s)
                        except Exception:  # noqa: BLE001
                            continue
                        for jpath, text in walk_strings(parsed):
                            for kw in FORBIDDEN:
                                if kw in text:
                                    hits.append(f"{t}.{col} rowid={rid} {jpath} 命中 {kw}")
    finally:
        c.close()
    return hits


def main() -> int:
    if not SRC_DB.exists():
        print(f"[ERR] 源库不存在: {SRC_DB}")
        return 1

    SEED_DIR.mkdir(parents=True, exist_ok=True)
    if SEED_DB.exists():
        SEED_DB.unlink()
        print(f"[1/5] 已删除旧种子库")

    # 1. 整库复制
    c = sqlite3.connect(str(SRC_DB))
    c.execute("VACUUM INTO ?", (str(SEED_DB),))
    c.close()
    print(f"[1/5] 整库复制完成 -> {SEED_DB}（{SEED_DB.stat().st_size / 1024 / 1024:.1f} MB）")

    # 2. 在副本里做减法
    c = sqlite3.connect(str(SEED_DB))
    c.execute("PRAGMA secure_delete=ON")

    # 2a. 清掉 source_url（可能带爬虫追踪参数，公开无意义）
    n_jd = c.execute("select count(*) from jds").fetchone()[0]
    c.execute("update jds set source_url = NULL")
    # 2b. 只保留虚构简历（id=1），并抹掉指向本地文件的路径
    c.execute("delete from resumes where id != 1")
    c.execute("update resumes set storage_path = NULL")
    keep_resume = c.execute("select count(*) from resumes").fetchone()[0]
    # 2c. 只保留 mock provider，且不留任何密钥字段
    c.execute("delete from llm_providers where provider_type != 'mock'")
    c.execute("update llm_providers set api_key_encrypted = NULL")
    n_prov = c.execute("select count(*) from llm_providers").fetchone()[0]
    # 2d. 删掉运行期日志表
    for t in ("evaluation_logs",):
        try:
            c.execute(f"delete from {t}")
        except sqlite3.OperationalError:
            pass
    c.commit()

    # 3. 清空闲页残留
    c.execute("VACUUM")
    c.commit()
    n_cust = c.execute("select count(*) from customizations").fetchone()[0]
    n_vec = c.execute("select count(*) from resume_vectors").fetchone()[0]
    c.close()
    print(
        f"[2/5] 清理完成：jds {n_jd} 条（source_url 已清空）、"
        f"resumes {keep_resume} 份、customizations {n_cust} 条、"
        f"resume_vectors {n_vec} 条、providers {n_prov} 个"
    )

    # 4. PII 闸门
    print("[3/5] PII 扫描中…")
    hits = scan_pii(SEED_DB)
    if hits:
        print(f"[ERR] 种子库仍含敏感信息，**未产出**（已删除）：")
        for h in hits[:20]:
            print(f"      - {h}")
        SEED_DB.unlink(missing_ok=True)
        return 2
    print(f"[4/5] PII 扫描通过：{len(FORBIDDEN)} 个关键词 × 全表（含 JSON 解析）0 命中")

    size_mb = SEED_DB.stat().st_size / 1024 / 1024
    print(f"[5/5] 种子库就绪：{SEED_DB}")
    print(f"      体积 {size_mb:.1f} MB | SHA256 见下")
    import hashlib

    print(f"      {hashlib.sha256(SEED_DB.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
