# JD Resume Platform

这是一个本地优先的简历定制平台：后端用 FastAPI + SQLite，LLM 默认走 mock provider，前端直接用 Vite 启动，不依赖 Docker、Redis、Celery、Postgres 或外部服务。

## 1. 目标

- Windows 本地双击打开即可运行
- 默认使用 SQLite，本地数据文件保存在 `backend/data/jd_platform.db`
- 默认启用爬虫，但可通过 `CRAWLER_ENABLED=false` 关闭
- 默认 LLM provider 为 `mock`，离线可用
- 保留 LangChain（OpenAI / Anthropic 真实接入仍可用）

## 2. 目录说明

- `backend/`：FastAPI 后端（`backend/data/` 存放本地数据库与简历文件）
- `frontend/`：React + Vite 前端
- `start.bat`：Windows 双击启动脚本
- `backend/.env.example`：环境变量示例（应用实际读取的是 `backend/.env`）
- `docs/`：设计文档

## 3. 一键启动（Windows）

在项目根目录直接双击运行：

```bat
start.bat
```

脚本会自动执行：

1. 创建 `backend/.venv`
2. 安装后端依赖
3. 安装前端依赖
4. 启动后端：`http://localhost:8000/docs`
5. 启动前端：`http://localhost:5173`

## 4. 手动启动

### 后端

```bat
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 前端

```bat
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

## 5. 环境变量

配置模板是 `backend/.env.example`，**必须先进 `backend/` 目录**再复制。

原因：`app/core/config.py` 里的 `env_file=".env"` 是相对路径，相对进程工作目录解析，而以 `start.bat` 方式启动时工作目录就是 `backend/`。根目录下的 `.env` 不会被读取。

```bat
cd backend
copy .env.example .env
```

默认示例已切换成 SQLite：

```env
DATABASE_URL=sqlite+aiosqlite:///./data/jd_platform.db
DATABASE_SYNC_URL=sqlite:///./data/jd_platform.db
LLM_DEFAULT_PROVIDER=mock
CRAWLER_ENABLED=true
```

> 注意：这里的 `./data/...` 是相对 `backend/` 的路径，即实际落在 `backend/data/`。

## 6. 本地开发与测试

### 后端测试

```bat
cd backend
.venv\Scripts\python.exe -m pytest tests/ -v
```

### 前端构建

```bat
cd frontend
npm run build
```

## 7. 数据位置

默认数据库文件：

```text
backend/data/jd_platform.db
```

简历原文件默认目录：

```text
backend/data/resumes/
```

## 8. LLM 模式

默认模式为 `mock`，无需 OpenAI / Anthropic Key 即可本地运行。

如果要接真实模型，可在 `LLM_DEFAULT_PROVIDER` 里切成 `openai` 或 `anthropic`，并填写对应 API Key。

> **粘贴 JD 的结构化抽取怎么工作？**
> - 默认（`mock`）：走**规则抽取**（`app/services/heuristic_extract.py`），
>   用正则 + 段落切分 + 技能词典抽出职位 / 公司 / 城市 / 薪资 / 学历 / 经验 /
>   技能 / 职责 / 要求，结果里标记 `structured.extract_mode = "heuristic"`。
> - 配置了真实 provider 后：自动切回 LLM 路径，标记为 `"llm"`。
>
> 换句话说，**没有 API Key 也能用「粘贴 → 结构化」**，只是精度不如真实模型。

## 9. 说明

- 当前版本已去掉 Docker / Redis / Celery / PostgreSQL 依赖
- 爬虫保留并默认启用，适合本地抓取 JD
- API 仍兼容统一 `Result` 响应格式，前后端交互保持一致

## 10. 岗位数据抓取（可选）

内置牛客 / Boss 直聘的 JD 抓取能力，数据写入 `backend/data/jd_platform.db` 的 `jds` 表。

**网页端（「在招岗位」页）** 可以直接用：

- 右上角**「抓取最新岗位」** → 走牛客公开接口，几秒入库 60 条；输入框里有关键词时会带上该关键词检索
- **筛选栏**：关键词（岗位/公司/城市模糊匹配）、城市、学历、薪资区间、来源、排序、只看有薪资
- 岗位卡片支持**查看详情**（含职责 / 要求 / 原始 JD 全文）、**重新解析**、打开原岗位、删除
- 右侧可**粘贴 JD 文本**做结构化，或提交单个职位 URL 抓取

### 10.1 批量抓取

```bat
REM 牛客 + Boss，共 100 条
backend\.venv\Scripts\python.exe scripts\crawl_jobs.py --limit 100

REM 只抓牛客，走官方接口（推荐：1 次请求即可拿 100 条）
backend\.venv\Scripts\python.exe scripts\crawl_jobs.py --source nowcoder --limit 100

REM 只抓 Boss
backend\.venv\Scripts\python.exe scripts\crawl_jobs.py --source boss --query Python --city 100010000 --limit 50

REM 只取列表、不入库
backend\.venv\Scripts\python.exe scripts\crawl_jobs.py --source nowcoder --limit 20 --dry-run
```

| 参数 | 说明 |
|---|---|
| `--limit N` | 目标总条数（默认 100）；超过 300 需加 `--yes` |
| `--source nowcoder \| boss \| all` | 抓取来源 |
| `--nowcoder-mode api \| dom` | 牛客抓取方式；`api`（默认）走官方接口，`dom` 逐页渲染 |
| `--nowcoder-scope school \| full` | `school`=按招聘类型（去重约 450 条）；`full`=分类+关键词+多端点（**实测 4803 条**） |
| `--nowcoder-recruit-type` | 牛客招聘类型：数字、逗号分隔（如 `1,2`）、或 `all`（0/1/2/3 合并去重） |
| `--delay` | 请求间隔秒数（默认 1.5），**请勿设为 0** |
| `--structure` | 抓完后额外跑一次 LLM 结构化（默认关闭） |
| `--user-data-dir` / `--storage-state` | 复用已登录会话（Boss 需要） |

**全量抓取（推荐）**——走 `square-search` 的关键词检索，实测单次拿到 **4803 条去重职位**：

```bat
backend\.venv\Scripts\python.exe scripts\crawl_jobs.py --source nowcoder ^
  --nowcoder-scope full --limit 6000 --yes
```

> **为什么需要关键词检索？**
> `recruitType` 只有 `0/1/2/3` 返回不同数据（去重 447 条），填 `4~30` 都会回落到
> 与 `1` 相同的 200 条。真正能扩开数据量的是接口的 `query` 关键词参数
> ——26 个关键词就把去重总量从 447 推到 2581。`--nowcoder-scope full` 会用
> 107 个关键词种子逐个检索，并叠加 `/u/job/search`、`/u/job/list` 两个列表端点，
> 连续 15 个关键词无新增时自动停止。实测耗时约 3.5 分钟、250 次低频请求
> （默认 0.35s 间隔），得到 **4803 条唯一职位**。

> **薪资单位说明**：牛客有两种薪资口径，由 `salaryType` 区分（实测 100% 对应）——
> `2` 为月薪（K/月），`1` 为日薪（元/天）。`salary_min/salary_max` 两列在系统里
> 按「月薪 K」呈现，因此**日薪岗位的数值列留空**，原始文本存在
> `structured.crawl_meta.salary_display` 并写入正文，避免出现「500-550K」这类误导值。

### 10.2 清理重复行

```bat
REM 预览（默认不改数据）
backend\.venv\Scripts\python.exe scripts\dedupe_jds.py

REM 确认后执行
backend\.venv\Scripts\python.exe scripts\dedupe_jds.py --apply
```

### 10.3 校验数据真实性

抓完后建议跑一次校验：它会**独立打开每个职位的真实详情页**，
从页面内嵌数据里取出站点自己渲染的字段，与库中记录逐字段比对
（职位名、公司 ID、薪资、城市、学历、正文），确认没有脏数据。

```bat
REM 静态校验（全量、不联网）
backend\.venv\Scripts\python.exe scripts\verify_jds.py

REM 抽样 15 条联网比对真实页面
backend\.venv\Scripts\python.exe scripts\verify_jds.py --live 15

REM 全量联网比对（约 4-5 分钟）
backend\.venv\Scripts\python.exe scripts\verify_jds.py --all-live
```

### 10.4 Boss 直聘说明（重要）

**当前环境下 Boss 无法抓取**，排查结论如下：

- 其搜索接口对无会话访问统一返回 `{"code":35,"message":"您的IP地址存在异常行为."}`。
  实测更换 `Accept` / `Referer` / `Origin` / `X-Requested-With` 等请求头**均无效**，
  判定发生在 IP / 会话层，不是请求头能解决的。
- Boss 的 `robots.txt` 明确 `Disallow: /*?query=*`、`*?city=*`、`*?experience=*` 等，
  **不欢迎对搜索结果做抓取**，并专门封禁了 `Jobuispider` 这类职位爬虫 UA。
- 官方开放平台（`hi-open.zhipin.com`）面向**企业招聘方**，需创建应用、申请权限、
  申请 IP 白名单，**没有面向求职者的职位搜索接口**。

唯一有技术希望的路子是**复用你自己账号的登录态**：

```bat
REM 1) 检查依赖与配置（不开浏览器）
backend\.venv\Scripts\python.exe scripts\boss_login.py --check

REM 2) 打开浏览器手动登录，脚本自动检测能否看到职位并保存会话
backend\.venv\Scripts\python.exe scripts\boss_login.py

REM 3) 小批量验证（先别全量）
backend\.venv\Scripts\python.exe scripts\crawl_jobs.py --source boss ^
  --storage-state backend\data\boss_state.json --limit 10 --dry-run
```

> **请自行评估风险**：用账号低频抓取仍与 Boss 的 robots 条款存在张力，
> 最坏情况是账号被风控。建议只抓自己求职真正需要的岗位。
>
> 项目**不做任何绕过**：不轮换 IP、不破解 `__zp_stoken__` 签名、不伪造浏览器指纹。

### 10.5 已知限制

- **牛客**：可用，走官方接口，速度快。
- **Boss 直聘**：见 10.4，需自备登录态且存在条款风险。
- 请遵守目标站点的 robots 与服务条款，仅用于个人求职分析，保持低频访问。
