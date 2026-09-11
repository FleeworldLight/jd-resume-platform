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

## 9. 说明

- 当前版本已去掉 Docker / Redis / Celery / PostgreSQL 依赖
- 爬虫保留并默认启用，适合本地抓取 JD
- API 仍兼容统一 `Result` 响应格式，前后端交互保持一致

## 10. 岗位数据抓取（可选）

内置牛客 / Boss 直聘的 JD 抓取能力，数据写入 `backend/data/jd_platform.db` 的 `jds` 表。

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
| `--delay` | 请求间隔秒数（默认 1.5），**请勿设为 0** |
| `--structure` | 抓完后额外跑一次 LLM 结构化（默认关闭） |
| `--user-data-dir` | 持久化浏览器目录，可复用已登录会话（Boss 需要） |

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

### 10.4 已知限制

- **牛客**：可用，走官方接口，速度快。
- **Boss 直聘**：其搜索/列表接口对数据中心与代理 IP 有风控，会返回
  `{"code":35,"message":"您的IP地址存在异常行为."}`。家庭宽带下或复用已登录会话
  （`--user-data-dir`）可能可用，需自行验证。脚本会如实报错，不会伪造数据。
- 请遵守目标站点的 robots 与服务条款，仅用于个人求职分析，保持低频访问。
