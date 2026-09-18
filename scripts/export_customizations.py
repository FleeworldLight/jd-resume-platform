"""把数据库里的「定制简历」导出成实体文件（离线，不需要启动后端）。

产物说明（2026-09 改版）
------------------------
定制化的产物是**一份简历**，但它只保存在 SQLite 的
``customizations.customized_resume`` 这个 JSON 列里，磁盘上没有文件。
前端「下载简历 PDF / DOCX」是实时渲染后推给浏览器的，落在浏览器下载目录。

本脚本绕过 HTTP，直接读库 + 复用同一套渲染函数落盘，方便备份、批量导出。
与线上导出**逐字节一致**（同一份 ``tailored_to_text`` 文本）。

用法（在仓库根目录执行）：::

    backend\\.venv\\Scripts\\python.exe scripts\\export_customizations.py
    backend\\.venv\\Scripts\\python.exe scripts\\export_customizations.py --id 4
    backend\\.venv\\Scripts\\python.exe scripts\\export_customizations.py --report --out D:\\简历

产出：``backend/data/customizations/简历_<姓名>_<岗位>.pdf / .docx``
（加 ``--report`` 会额外导出分析报告 PDF）
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "backend" / "data" / "jd_platform.db"
DEFAULT_OUT = ROOT / "backend" / "data" / "customizations"

_ILLEGAL = '\\/:*?"<>|'


def _safe(name: str) -> str:
    for ch in _ILLEGAL:
        name = name.replace(ch, "_")
    return " ".join(name.split()).strip() or "未命名"


class _Record:
    """把 sqlite3.Row 包装成渲染函数需要的对象（鸭子类型）。"""

    def __init__(self, row: sqlite3.Row) -> None:
        self.id = row["id"]
        self.status = row["status"]
        self.provider_used = row["provider_used"]
        self.jd_id = row["jd_id"]
        for col in (
            "gap_report",
            "customized_resume",
            "prediction",
            "retrieval_metrics",
            "matched_resumes",
        ):
            raw = row[col]
            if raw is None:
                setattr(self, col, {} if col != "matched_resumes" else [])
                continue
            try:
                setattr(self, col, json.loads(raw))
            except (TypeError, ValueError):
                setattr(self, col, {} if col != "matched_resumes" else [])


def main() -> int:
    ap = argparse.ArgumentParser(description="导出定制简历为 PDF / DOCX")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="SQLite 数据库路径")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录")
    ap.add_argument("--id", type=int, default=None, help="只导出指定 ID")
    ap.add_argument("--report", action="store_true", help="额外导出分析报告 PDF")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"[ERR] 找不到数据库: {db_path}")
        return 1

    # 让 scripts/ 能 import 到 backend/app
    sys.path.insert(0, str(ROOT / "backend"))
    try:
        from app.schemas.customization import TailoredResume
        from app.services.tailor_pipeline import tailored_to_text
        from app.utils.docx import render_text_docx
        from app.utils.pdf import render_customization_pdf, render_resume_pdf
    except Exception as exc:  # noqa: BLE001
        print(f"[ERR] 无法加载渲染模块（请用 backend 的 venv 运行）: {exc}")
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    sql = """
        SELECT c.*, j.position AS jd_position, j.company AS jd_company
        FROM customizations c
        LEFT JOIN jds j ON j.id = c.jd_id
    """
    params: tuple = ()
    if args.id is not None:
        sql += " WHERE c.id = ?"
        params = (args.id,)
    sql += " ORDER BY c.id"

    rows = list(conn.execute(sql, params))
    if not rows:
        scope = f"ID={args.id}" if args.id is not None else "全部"
        print(f"没有找到定制化记录（{scope}）。")
        return 0

    ok = 0
    for row in rows:
        rec = _Record(row)
        data = rec.customized_resume
        if not isinstance(data, dict) or not data.get("content"):
            print(f"[SKIP] #{rec.id} 是旧版「报告格式」记录，没有简历正文；"
                  f"请在网页上重新发起一次定制化。")
            continue
        try:
            t = TailoredResume.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            print(f"[ERR] #{rec.id} 简历结构解析失败: {exc}")
            continue

        text = tailored_to_text(t, include_unconfirmed=True)
        name = t.content.basics.name or f"定制{rec.id:02d}"
        pos = t.target_position or t.content.profile.title or "目标岗位"
        # 带 ID 前缀：不同 JD 可能解析出同名岗位，避免互相覆盖
        stem = f"简历{rec.id:02d}_{_safe(name)}_{_safe(pos)}"

        try:
            (out_dir / f"{stem}.pdf").write_bytes(render_resume_pdf(text, title=""))
            (out_dir / f"{stem}.docx").write_bytes(render_text_docx(text, title=""))
            if args.report:
                (out_dir / f"{stem}_分析报告.pdf").write_bytes(
                    render_customization_pdf(rec)
                )
        except Exception as exc:  # noqa: BLE001
            print(f"[ERR] #{rec.id} 渲染失败: {exc}")
            continue

        pending = sum(1 for s in t.suggestions if not s.confirmed)
        ok += 1
        print(f"[OK ] {stem}.pdf / .docx"
              f"  （{len(text)} 字符，{pending} 项待确认）")

    print(f"\n共导出 {ok}/{len(rows)} 份 -> {out_dir}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
