# 脚本说明

> 全部在**仓库根目录**执行，解释器用 `backend\.venv\Scripts\python.exe`。
> 这些脚本直接读写生产数据库 `backend/data/jd_platform.db`，跑之前请先看说明。

## 一览

| 脚本 | 用途 | 是否联网 | 是否写库 |
|---|---|---|---|
| [crawl_jobs.py](crawl_jobs.py) | 批量抓取岗位 JD 并入库 | ✅ 牛客 | ✅（新增/更新） |
| [verify_jds.py](verify_jds.py) | 校验库内岗位数据与真实页面一致 | 静态部分不联网 | ❌ 只读 |
| [dedupe_jds.py](dedupe_jds.py) | 合并 URL 规范化后重复的岗位行 | ❌ | ⚠️ 默认只预览，`--apply` 才写 |
| [boss_login.py](boss_login.py) | 打开浏览器登录 Boss，保存会话供抓取复用 | ✅ | 只写会话文件 |
| [export_demo_seed.py](export_demo_seed.py) | 导出**脱敏种子库**（部署用，含 PII 闸门） | ❌ | 只写 `backend/seed/` |
| [export_static_demo.py](export_static_demo.py) | 导出**静态演示 JSON**（Pages 无后端时用） | ❌ | 只写 `frontend/public/demo-data/` |
| [prepare_hf_space.py](prepare_hf_space.py) | 生成可直接推送到 Hugging Face Spaces 的目录 | ❌ | 只写仓库外的 `_hf_space/` |

## crawl_jobs.py —— 批量抓取

```bat
REM 只抓牛客（官方接口，1 次请求可拿 200 条）
backend\.venv\Scripts\python.exe scripts\crawl_jobs.py --source nowcoder --limit 100

REM 牛客全量（分类 + 关键词 + 多端点，实测 4803 条去重职位，约 3.5 分钟）
backend\.venv\Scripts\python.exe scripts\crawl_jobs.py --source nowcoder --nowcoder-scope full --limit 6000 --yes

REM 只看会抓到什么，不入库
backend\.venv\Scripts\python.exe scripts\crawl_jobs.py --source nowcoder --limit 20 --dry-run
```

要点：

- 牛客走的是**站点前端自己调用的公开接口**（`/np-api/u/job/square-search`），
  `recruitType` 只有 `0/1/2/3` 返回不同数据，`query` 关键词才是扩展数据量的杠杆。
- 目标超过 300 条必须显式加 `--yes`。
- **不要把 `--delay` 设为 0**；默认已限速。
- 薪资口径：`salaryType=2` 月薪(K) 写数值列；`=1` 日薪(元/天)**不折算**，
  数值列留空、原文进 `crawl_meta.salary_display`。

## verify_jds.py —— 数据真实性校验

```bat
backend\.venv\Scripts\python.exe scripts\verify_jds.py             REM 静态校验（全量、不联网）
backend\.venv\Scripts\python.exe scripts\verify_jds.py --live 15   REM 抽样比对真实页面
backend\.venv\Scripts\python.exe scripts\verify_jds.py --all-live  REM 全量比对（约 4-5 分钟）
```

原理：直接请求每个职位的详情页，从 `window.__INITIAL_STATE__.store.jobDetail.detail`
取出**站点自己渲染**的字段，与库内记录逐字段比对（职位名 / 公司 ID / 薪资 / 城市 / 学历 / 正文）。
建议**每次全量抓取后跑一次**，作为入库数据的质量门禁。

## dedupe_jds.py —— 重复行清理

```bat
backend\.venv\Scripts\python.exe scripts\dedupe_jds.py            REM 预览（默认）
backend\.venv\Scripts\python.exe scripts\dedupe_jds.py --apply    REM 确认后执行
```

背景：早期 DOM 抓取入库的 URL 带 query 参数，与接口路径的规范 URL 会被当成两条。
本脚本按规范化后的 URL 找出重复组，保留字段最全的一行、合并其余。
**默认只打印预览，不加 `--apply` 不会动数据库。**

## boss_login.py —— Boss 直聘登录态
```bat
backend\.venv\Scripts\python.exe scripts\boss_login.py --check   REM 检查依赖与配置
backend\.venv\Scripts\python.exe scripts\boss_login.py           REM 打开浏览器手动登录
```

打开可见浏览器让你手动扫码，自动检测搜索页能否渲染职位卡片；成功后会话存到
`backend/data/boss_state.json`，抓取时用 `--storage-state` 复用。

> **风险自担**：Boss 的 robots 明确不欢迎抓取搜索结果，用账号自动化访问最坏情况是账号被风控。
> 项目**不做任何绕过**（不换 IP、不破解签名、不伪造指纹）。

## export_demo_seed.py —— 导出脱敏种子库（部署用）

```bat
backend\.venv\Scripts\python.exe scripts\export_demo_seed.py
```

产出 `backend/seed/demo_seed.db`（约 12MB，**需要提交进仓库**）。
免费云平台的磁盘是临时的，后端启动时若发现数据文件不存在，会直接复制这份种子库
（见 `backend/app/db/init_db.py`），从而实现「冷启动即有数据」。

做法是 `VACUUM INTO` 整库复制后在副本里做减法（清空 `source_url`、只留虚构简历与
mock provider），并内置 **JSON 感知的 PII 闸门**——命中姓名/手机/邮箱/GitHub/学校
等关键词就报错退出、**不产出种子库**。

## export_static_demo.py —— 导出静态演示 JSON（Pages 用）

```bat
backend\.venv\Scripts\python.exe scripts\export_static_demo.py
```

产出 `frontend/public/demo-data/*.json`（**需要提交进仓库**）。
GitHub Pages 上没有后端时，前端 `src/demoData.ts` 会读这些文件在浏览器里应答请求，
所以演示站不依赖任何服务器也能看完整界面。

不手写字段映射，而是**用进程内的 ASGI 客户端调用真实接口**再落盘，
保证导出结构与线上接口逐字段一致。产出约 6.8MB（gzip 后约 1.2MB）。

## prepare_hf_space.py —— 准备 Hugging Face Space 目录

```bat
backend\.venv\Scripts\python.exe scripts\prepare_hf_space.py
```

HF Spaces 要求 **Dockerfile 位于仓库根**、且根目录要有带 YAML front-matter 的
`README.md`（声明 `sdk: docker`）。本脚本把这些收拾好，在**仓库外**生成 `_hf_space/`，
之后 `cd` 进去 `git push` 即可。详细步骤见 [docs/deploy-huggingface.md](../docs/deploy-huggingface.md)。

## 通用注意

- 脚本与后端共用同一个 SQLite 文件；**服务正在运行时也可以跑**，但大量写入瞬间可能短暂锁库。
- 改脚本前先跑 `pytest`（59 项），别破坏已有行为。
- 这些脚本没有独立的测试覆盖，属"工具"性质；改动后用 `--dry-run` / `--limit 3` 先验证。
