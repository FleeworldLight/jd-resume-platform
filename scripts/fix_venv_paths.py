"""修复 / 加固虚拟环境里与盘符绑定的路径。

项目在 G: / E: 之间来回搬时，venv 有两处会失效：

1. ``pyvenv.cfg`` 的 ``home`` 指向已不存在的基础解释器
   → ``Scripts\\python.exe`` 一启动就报 ``did not find executable at ...``；
2. ``Scripts\\*.exe``（pip / uvicorn / pytest / alembic ...）是 pip 生成的启动器，
   尾部内嵌 ``#!<建环境时的绝对路径>``，换盘即全部失效（静默 exit 1、无任何输出）。

处置策略（目标是「搬盘之后自愈」）：

- **启动器统一改写成裸名 ``#!python.exe``**。
  distlib 启动器会在**自己所在的目录**里找解释器，所以 venv 搬到哪个盘、从哪个 cwd 调用、
  PATH 里有没有别的 python 都不受影响（已实测）。这样启动器以后再也不需要修。
- **``pyvenv.cfg`` 的 home 只在「当前 home 已失效」时才改写**，
  且要求候选解释器与 venv 记录的 3.x 版本一致；版本不符时明确报错而不是硬改
  —— 硬改会让 site-packages 里的 cp3xx 扩展模块整体崩掉。

用法：

    # venv 里的 python 已经跑不起来，所以用别的解释器执行本脚本
    X:\\Python314\\python.exe scripts/fix_venv_paths.py            # 只体检
    X:\\Python314\\python.exe scripts/fix_venv_paths.py --apply    # 实际修复

    # 指定 venv / 基础解释器 / 改用绝对路径 shebang
    python scripts/fix_venv_paths.py --venv backend/.venv --python E:/Python314/python.exe --apply
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ZIP_MAGIC = b"PK\x03\x04"
BARE_INTERPRETER = "python.exe"
DRIVE_SCAN = ["C", "D", "E", "F", "G", "H"]


def find_shebang(data: bytes) -> tuple[int, int] | None:
    """定位 pip 启动器尾部内嵌的 shebang，返回 (起点, 换行符位置)；不是启动器则返回 None。"""
    start = data.rfind(b"#!")
    if start < 0:
        return None
    newline = data.find(b"\n", start)
    if newline < 0 or data[newline + 1 : newline + 5] != ZIP_MAGIC:
        # 不是「#!路径 + zip」这种启动器结构，别乱动
        return None
    return start, newline


def rewrite_shebang(data: bytes, start: int, newline: int, interpreter: str) -> bytes:
    """重写 shebang。路径长度可以变：stub + 新 shebang + 原 zip 负载。"""
    return data[:start] + b"#!" + interpreter.encode("utf-8") + b"\n" + data[newline + 1 :]


def run_version(exe: Path) -> str | None:
    """返回解释器的 'X.Y' 版本号，跑不起来则返回 None。"""
    try:
        proc = subprocess.run(
            [str(exe), "-c", "import sys;print('%d.%d' % sys.version_info[:2])"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def read_cfg(cfg: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in cfg.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def candidates(venv: Path, explicit: str | None, cfg_home: str | None) -> list[Path]:
    """按优先级给出候选基础解释器（保持顺序、去重）。"""
    order: list[Path] = []
    if explicit:
        order.append(Path(explicit))
    if cfg_home:
        order.append(Path(cfg_home) / "python.exe")
    drive = (venv.drive or "").rstrip(":")
    for letter in ([drive] if drive else []) + DRIVE_SCAN:
        if letter:
            order.append(Path(f"{letter}:\\Python314\\python.exe"))
    order.append(Path(sys.executable))
    result: list[Path] = []
    for item in order:
        try:
            resolved = item.resolve()
        except OSError:
            resolved = item
        if resolved not in result:
            result.append(resolved)
    return result


def pick_base(venv: Path, cfg: dict[str, str], explicit: str | None) -> tuple[Path | None, list[str]]:
    """挑一个能跑、且版本和 venv 记录一致的解释器。返回 (解释器, 说明列表)。"""
    want_xy = ".".join(cfg.get("version", "").split(".")[:2])
    notes: list[str] = []
    for exe in candidates(venv, explicit, cfg.get("home")):
        if not exe.exists():
            continue
        xy = run_version(exe)
        if xy is None:
            notes.append(f"跳过（跑不起来）：{exe}")
            continue
        if want_xy and xy != want_xy:
            notes.append(f"跳过（版本 {xy} != venv 需要的 {want_xy}）：{exe}")
            continue
        return exe, notes
    return None, notes


def fix_launchers(scripts: Path, interpreter: str, apply: bool) -> list[str]:
    changes: list[str] = []
    for exe in sorted(scripts.glob("*.exe")):
        data = exe.read_bytes()
        found = find_shebang(data)
        if found is None:
            continue  # python.exe / pythonw.exe 这类本体，不是 pip 启动器
        start, newline = found
        old = data[start + 2 : newline].decode("utf-8", "surrogateescape")
        if old == interpreter:
            continue
        if apply:
            exe.write_bytes(rewrite_shebang(data, start, newline, interpreter))
        changes.append(f"{exe.name}: {old} -> {interpreter}")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description="修复/加固 venv 里与盘符绑定的路径")
    parser.add_argument("--venv", default="backend/.venv", help="虚拟环境目录（默认 backend/.venv）")
    parser.add_argument("--python", default=None, help="基础解释器 python.exe；默认自动探测")
    parser.add_argument("--apply", action="store_true", help="实际写盘（默认只体检）")
    parser.add_argument(
        "--absolute",
        action="store_true",
        help="启动器改写为绝对路径 shebang（默认写成盘无关的裸名 python.exe）",
    )
    args = parser.parse_args()

    venv = Path(args.venv).resolve()
    cfg = venv / "pyvenv.cfg"
    scripts = venv / "Scripts"
    if not cfg.is_file():
        print(f"[ERR] 找不到 {cfg}")
        return 1

    values = read_cfg(cfg)
    print(f"venv          : {venv}")
    print(f"venv 版本     : {values.get('version', '未知')}")
    print(f"当前 home     : {values.get('home', '（缺失）')}")
    print(f"模式          : {'修复' if args.apply else '体检（加 --apply 才会写盘）'}\n")

    # ---- 1) 启动器：改成盘无关的裸名 ----
    if args.absolute:
        interpreter = str(scripts / "python.exe")
        print(f"启动器 shebang：改用绝对路径 {interpreter}（仍与盘符绑定）")
    else:
        interpreter = BARE_INTERPRETER
        print(f"启动器 shebang：改用裸名 {interpreter}（在启动器自己所在目录找解释器 → 与盘符无关）")
    launcher_changes = fix_launchers(scripts, interpreter, args.apply)
    for line in launcher_changes:
        print("  改 " + line)
    if not launcher_changes:
        print("  无需改动")

    # ---- 2) pyvenv.cfg：只有 home 失效才改写 ----
    print()
    home_exe = Path(values["home"]) / "python.exe" if values.get("home") else None
    home_xy = run_version(home_exe) if home_exe and home_exe.exists() else None
    want_xy = ".".join(values.get("version", "").split(".")[:2])
    if home_exe and home_xy and (not want_xy or home_xy == want_xy):
        print(f"pyvenv.cfg    : home 有效（{home_exe}，{home_xy}）→ 不改写")
    else:
        if home_exe and home_exe.exists():
            print(f"pyvenv.cfg    : home 版本不符（{home_xy} != {want_xy}）→ 需要改写")
        else:
            print(f"pyvenv.cfg    : home 已失效（{values.get('home', '缺失')}）→ 需要改写")
        base, notes = pick_base(venv, values, args.python)
        for note in notes:
            print("  " + note)
        if base is None:
            print(f"\n[ERR] 找不到可用的基础解释器（需要 Python {want_xy}）。")
            print("[ERR] 请把 Python 装到任意盘的 X:\\Python314，")
            print("[ERR] 或用 --python 指定一个匹配版本的 python.exe 后重跑。")
            print("[ERR] 若愿意重建环境（依赖需重装）：删掉 backend\\.venv 后重跑 start.bat。")
            return 1
        new_lines = {
            "home": str(base.parent),
            "executable": str(base),
            "command": f"{base} -m venv {venv}",
        }
        out: list[str] = []
        seen: set[str] = set()
        for line in cfg.read_text(encoding="utf-8").splitlines():
            key = line.split("=", 1)[0].strip() if "=" in line else ""
            if key in new_lines:
                seen.add(key)
                new_line = f"{key} = {new_lines[key]}"
                if new_line != line:
                    print(f"  改 pyvenv.cfg: {line} -> {new_line}")
                out.append(new_line)
            else:
                out.append(line)
        for key, value in new_lines.items():
            if key not in seen:
                out.append(f"{key} = {value}")
                print(f"  改 pyvenv.cfg: 补上 {key} = {value}")
        if args.apply:
            cfg.write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"  基础解释器：{base}")

    print(f"\n完成{'（已写盘）' if args.apply else '（未写盘，加 --apply 生效）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
