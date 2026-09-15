#!/usr/bin/env python
"""准备一个可直接推送到 Hugging Face Spaces 的目录。

为什么要这个脚本
----------------
HF Spaces 对仓库结构有两个硬要求，手动准备容易踩坑：

1. **Dockerfile 必须在仓库根目录** —— 而本项目的 Dockerfile 在 `backend/`
2. **仓库根必须有一份带 YAML front-matter 的 `README.md`**，用来声明 `sdk: docker`
   （本项目的 README.md 是给 GitHub 看的，不能直接用）

于是这里把 `backend/` 的内容复制到 `_hf_space/`（**仓库外**，避免污染 Git），
补上 Space 专用的 README.md，然后你只要 cd 进去 git push 就行。

用法
----
    backend\\.venv\\Scripts\\python.exe scripts\\prepare_hf_space.py

生成位置：仓库同级的 `_hf_space/`（已在 .gitignore 之外，注意别提交）
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
OUT = ROOT.parent / "_hf_space"

# Space 仓库根需要这份 README（front-matter 是 HF 的元数据声明）
SPACE_README = """---
title: JD Resume Platform Backend
emoji: 💼
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# JD Resume Platform —— 后端

这是 [JD Resume Platform](https://github.com/{repo}) 的 FastAPI 后端容器，
仅供前端演示站调用。完整项目（前端 + 数据抓取脚本 + 文档）请看上面的仓库。

- 应用端口：容器内固定监听 `$PORT`，默认 `7860`
- 数据：镜像内含脱敏种子库 `seed/demo_seed.db`，容器启动时若数据文件不存在会自动还原
- 演示模式：环境变量 `DEMO_MODE=true` 时，上传 / 删除 / 抓取等写操作会被拦截
- 默认 LLM provider 为 `mock`，不配置任何 API Key 即可运行（走本地规则兜底）

接口文档：部署完成后访问 `<你的域名>/docs`。
"""

SKIP = {
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "data",          # 本地运行数据，不进镜像（容器里用 seed/ 还原）
    "tests",
    ".git",
}

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass


def main() -> int:
    if not BACKEND.exists():
        print(f"[ERR] 找不到 backend 目录: {BACKEND}")
        return 1

    # 只清理上次生成的内容（这里是仓库外的临时目录，不是用户数据）
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    copied = 0
    for item in sorted(BACKEND.iterdir()):
        if item.name in SKIP:
            continue
        target = OUT / item.name
        if item.is_dir():
            shutil.copytree(item, target, ignore=shutil.ignore_patterns(*SKIP))
        else:
            shutil.copy2(item, target)
        copied += 1

    (OUT / "README.md").write_text(
        SPACE_README.format(repo="FleeworldLight/jd-resume-platform"),
        encoding="utf-8",
    )

    # 校验关键文件都在位
    required = ["Dockerfile", "requirements.txt", "app/main.py", "seed/demo_seed.db", "README.md"]
    print("=== 准备 HF Space 目录 ===")
    print(f"  输出目录: {OUT}")
    print(f"  复制条目: {copied}")
    print(f"  生成时间: {datetime.now():%Y-%m-%d %H:%M}")
    print()
    print("=== 关键文件校验 ===")
    ok = True
    for rel in required:
        exists = (OUT / rel).exists()
        ok = ok and exists
        size = ""
        if exists and (OUT / rel).is_file():
            size = f"（{(OUT / rel).stat().st_size / 1024:.0f} KB）"
        print(f"  {'✓' if exists else '✗'} {rel}{size}")

    if not ok:
        print()
        print("[ERR] 有关键文件缺失，请先跑 scripts/export_demo_seed.py 生成种子库")
        return 2

    print()
    print("=== 下一步：推到 Hugging Face Space ===")
    print("  1) 在 https://huggingface.co/new-space 新建 Space：")
    print("     SDK 选 Docker，硬件选 CPU basic（免费），可见性按需")
    print("  2) 在 HF 头像 → Settings → Access Tokens 建一个 write 权限的 token")
    print("  3) 执行（把 <用户名>/<space名> 换成你的）：")
    print()
    print(f'     cd "{OUT}"')
    print("     git init -b main")
    print("     git remote add space https://huggingface.co/spaces/<用户名>/<space名>")
    print("     git add .")
    print('     git commit -m "deploy: backend"')
    print("     git push space main      # 提示输入密码时粘 Access Token")
    print()
    print("  4) 在 Space 的 Settings → Variables and secrets 里加环境变量（见文档）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
