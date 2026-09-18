import csv, json, sqlite3
from pathlib import Path

# 数据库路径跟着脚本所在的目录走，不写死盘符（换盘/换目录后依然可用）
DB = Path(__file__).resolve().parent / "backend" / "data" / "jd_platform.db"

COLS = ["id", "company", "position", "city", "education", "experience",
        "salary_min", "salary_max", "source", "source_url", "crawl_status"]

con = sqlite3.connect(DB)
rows = con.execute(f"select {','.join(COLS)}, skills from jds order by id desc").fetchall()

with open("jds_export.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(COLS + ["skills"])
    for r in rows:
        # skills 是 JSON 数组，拍平成「Python、SQL」这种，Excel 里好读
        skills = "、".join(json.loads(r[-1]) or []) if r[-1] else ""
        w.writerow(list(r[:-1]) + [skills])

print(f"已导出 {len(rows)} 行")