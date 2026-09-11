#!/usr/bin/env python
"""Boss 直聘登录态准备 + 可行性诊断。

为什么需要这个
--------------
Boss 的搜索/列表接口对「未登录 + 无会话」的访问统一返回：

    {"code":35,"message":"您的IP地址存在异常行为."}

实测换任何请求头组合（Accept / Referer / Origin / XHR）都无效，
说明判定发生在 IP/会话层，而不是请求头。页面自身 JS 会生成
`__zp_stoken__` 之类的凭证，只有真实浏览器会话才带得出来。

因此本项目**不做任何绕过**（不轮换 IP、不破解签名、不伪造指纹），
而是复用**你自己账号的正常登录态**：本脚本打开一个可见浏览器窗口，
你手动扫码/账号登录，脚本检测到能正常看到职位后，把会话保存下来，
后续 `crawl_jobs.py --storage-state` 复用。

⚠️ 请先阅读：合规与风险
----------------------
* Boss 的 robots.txt 中 `Disallow: /*?query=*` 与 `*?city=*` 等，
  **明确不欢迎对搜索结果做抓取**（还专门封禁了 `Jobuispider` 这类职位爬虫 UA）。
* 用自己账号低频抓取仍与该条款存在张力，**风险由你自行评估**，
  最坏情况是账号被风控。建议只抓自己求职真正需要的岗位，保持低频。
* 本脚本不注入任何反检测代码，也不隐藏自动化特征。

用法（在仓库根目录执行，需要图形界面，会弹出浏览器窗口）

    REM 只检查依赖与配置，不开浏览器
    backend\\.venv\\Scripts\\python.exe scripts\\boss_login.py --check

    REM 正式执行：打开浏览器 → 你登录 → 自动检测 → 保存会话
    backend\\.venv\\Scripts\\python.exe scripts\\boss_login.py

    REM 指定关键词/城市做能力验证（默认 Python / 北京）
    backend\\.venv\\Scripts\\python.exe scripts\\boss_login.py --query Java --city 101020100

成功后会生成 `backend/data/boss_state.json`（已被 .gitignore 忽略，不会提交）。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass

LOGIN_URL = "https://www.zhipin.com/web/user/?ka=header-login"
DEFAULT_STATE = BACKEND / "data" / "boss_state.json"

# 职位卡片的选择器（Boss 改版频繁，多写几个兜底）
CARD_SELECTORS = (
    ".job-card-wrapper",
    ".job-list-box li",
    "[class*='job-card']",
    ".job-list-wrapper li",
)

# 出现这些字样说明仍被风控或未登录
BLOCK_HINTS = ("异常行为", "安全验证", "请先登录", "登录后查看", "验证码")


def build_search_url(query: str, city: str) -> str:
    return (
        "https://www.zhipin.com/web/geek/job"
        f"?query={quote(query)}&city={city}"
    )


def check_mode() -> int:
    print("=" * 70)
    print("  依赖与配置检查（不启动浏览器）")
    print("=" * 70)
    ok = True
    try:
        import playwright  # noqa: F401

        print("  playwright      : OK")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"  playwright      : 缺失 ({exc})")

    # 注意：本函数可能在 asyncio 事件循环内被调用，
    # 不能用 sync_playwright()（会报 "Sync API inside the asyncio loop"），
    # 因此直接检查 Playwright 的浏览器缓存目录。
    browsers_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    if browsers_dir.is_dir():
        found = sorted(p.name for p in browsers_dir.glob("chromium*") if p.is_dir())
        if found:
            print(f"  chromium 缓存   : OK  {found}")
        else:
            ok = False
            print(f"  chromium 缓存   : {browsers_dir} 下没有 chromium*")
            print("                    可执行：python -m playwright install chromium")
    else:
        ok = False
        print(f"  chromium 缓存   : 未找到 {browsers_dir}")
        print("                    可执行：python -m playwright install chromium")

    print(f"  会话文件目标    : {DEFAULT_STATE}")
    print(f"  目录可写        : {os.access(DEFAULT_STATE.parent, os.W_OK)}")
    print(f"  登录页          : {LOGIN_URL}")
    print("\n  结论：" + ("可以继续，直接运行不带 --check 的命令" if ok else "请先修复上面标出的问题"))
    return 0 if ok else 1


async def count_cards(page) -> tuple[int, str]:
    """返回 (最大职位卡片数, 命中的选择器)。"""
    best, best_sel = 0, ""
    for sel in CARD_SELECTORS:
        try:
            n = await page.locator(sel).count()
        except Exception:  # noqa: BLE001
            n = 0
        if n > best:
            best, best_sel = n, sel
    return best, best_sel


async def probe(page, search_url: str) -> tuple[int, str, str]:
    """打开搜索页并诊断。返回 (卡片数, 选择器, 诊断文本)。"""
    await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(5000)
    try:
        await page.mouse.wheel(0, 3000)
        await page.wait_for_timeout(2500)
    except Exception:  # noqa: BLE001
        pass

    cards, sel = await count_cards(page)
    try:
        body = (await page.inner_text("body")) or ""
    except Exception:  # noqa: BLE001
        body = ""

    diag = ""
    if cards == 0:
        hit = [h for h in BLOCK_HINTS if h in body]
        if hit:
            diag = f"页面出现风控/登录提示: {hit}"
        elif len(body.strip()) < 100:
            diag = f"页面内容为空（{len(body.strip())} 字），可能仍在跳转"
        else:
            diag = f"页面有内容（{len(body.strip())} 字）但没有职位卡片，选择器可能已改版"
    return cards, sel, diag


async def main() -> int:
    parser = argparse.ArgumentParser(description="Boss 直聘登录态准备与可行性诊断")
    parser.add_argument("--check", action="store_true", help="只检查依赖，不开浏览器")
    parser.add_argument("--query", default="Python", help="验证用搜索关键词")
    parser.add_argument("--city", default="100010000", help="验证用城市码（100010000=北京）")
    parser.add_argument("--out", default=str(DEFAULT_STATE), help="会话文件保存路径")
    parser.add_argument("--timeout", type=int, default=480, help="等待登录的最长秒数")
    args = parser.parse_args()

    if args.check:
        return check_mode()

    from playwright.async_api import async_playwright

    search_url = build_search_url(args.query, args.city)
    out_path = Path(args.out)

    print("=" * 70)
    print("  Boss 直聘登录态准备")
    print("=" * 70)
    print("  即将打开一个浏览器窗口，请在其中完成登录（扫码或账号密码）。")
    print("  登录成功后本脚本会自动检测，检测通过即保存会话并退出。")
    print()
    print("  提醒：Boss 的 robots.txt 不欢迎抓取搜索结果，请自行评估风险；")
    print("        建议只抓个人求职需要的岗位并保持低频。")
    print("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = await ctx.new_page()

        print(f"\n[1/2] 打开登录页: {LOGIN_URL}")
        try:
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
        except Exception as exc:  # noqa: BLE001
            print(f"      打开登录页失败: {type(exc).__name__}: {str(exc)[:160]}")

        print(f"[2/2] 等待登录并验证搜索能力（最长 {args.timeout}s）…")
        print(f"      验证地址: {search_url}\n")

        waited = 0
        interval = 12
        last_diag = ""
        while waited < args.timeout:
            await asyncio.sleep(interval)
            waited += interval
            try:
                cards, sel, diag = await probe(page, search_url)
            except Exception as exc:  # noqa: BLE001
                print(f"  [{waited:>4}s] 探测异常: {type(exc).__name__}: {str(exc)[:110]}")
                continue

            print(f"  [{waited:>4}s] 职位卡片 {cards} 个" + (f"（{sel}）" if sel else "") + (f"  {diag}" if diag else ""))
            last_diag = diag

            if cards > 0:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                await ctx.storage_state(path=str(out_path))
                print("\n" + "=" * 70)
                print(f"  成功：能看到 {cards} 个职位卡片，登录态已保存到")
                print(f"        {out_path}")
                print()
                print("  下一步（先小批量验证，别直接全量）：")
                print("    backend\\.venv\\Scripts\\python.exe scripts\\crawl_jobs.py \\")
                print(f"      --source boss --query {args.query} --city {args.city} \\")
                print(f"      --storage-state \"{out_path}\" --limit 10 --dry-run")
                print("=" * 70)
                await browser.close()
                return 0

        print("\n" + "=" * 70)
        print("  未能在超时前检测到职位卡片。请把上面的诊断信息反馈回来。")
        if last_diag:
            print(f"  最后诊断: {last_diag}")
        print("  排查方向：")
        print("   1. 确认浏览器窗口里已真正登录（右上角出现头像）")
        print("   2. 若页面出现「安全验证」，需先在浏览器里手动过验证")
        print("   3. 若始终提示「IP 地址存在异常行为」，说明该网络出口被风控，")
        print("      换网络（家庭宽带）再试，或放弃 Boss 只用牛客")
        print("=" * 70)
        await browser.close()
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
