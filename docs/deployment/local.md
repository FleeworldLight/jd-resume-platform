# 本地部署

> 本地优先方案：SQLite + mock LLM provider，Windows 双击 `start.bat` 即可运行。
> 不需要 Docker / PostgreSQL / Redis / Celery，也不需要任何外部服务。

---

## 1. 环境要求

| 依赖 | 版本 | 必需 | 说明 |
|---|---|---|---|
| Windows | 10 / 11 | 是 | 启动脚本为 .bat |
| Python | 3.12+ | 是 | 后端运行时 |
| Node.js | 18+ | 是 | 前端运行时 |
| Playwright Chromium | 随依赖安装 | 否 | 仅在 `CRAWLER_ENABLED=true` 抓取 JD 时需要 |

不再需要 Docker / Docker Compose / PostgreSQL / Redis / Celery。

---

## 2. 目录结构

```text
jd-resume-platform/
├── backend/                  # FastAPI 后端
│   ├── app/                  # 应用代码（api / services / db / crawler / prompts）
│   ├── tests/                # pytest 测试
│   ├── alembic/              # 数据库迁移
│   ├── requirements.txt
│   ├── .env.example          # 环境变量模板（应用实际读取 backend/.env）
│   └── data/                 # 本地数据目录（git ignore）
│       ├── jd_platform.db    # SQLite 数据库
│       └── resumes/          # 简历原文件
├── frontend/                 # React + Vite 前端
├── docs/                     # 设计文档
├── start.bat                 # Windows 一键启动
└── README.md
```

---

## 3. 一键启动（推荐）

在项目根目录双击 `start.bat`。脚本会依次：

1. 释放 8000 / 5173 端口占用
2. 首次运行时创建 `backend/.venv` 并安装后端依赖
3. 首次运行时安装 Playwright Chromium
4. 首次运行时执行 `npm install`
5. 分别启动后端与前端（两个独立窗口）

访问地址：

- 前端：`http://localhost:5173`
- 后端 API 文档：`http://localhost:8000/docs`
- 本地数据库：`backend/data/jd_platform.db`
- 默认 LLM provider：`mock`

---

## 4. 手动启动

### 4.1 后端

```bat
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4.2 前端

```bat
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

前端 `vite.config.ts` 已把 `/api` 代理到 `http://localhost:8000`。

---

## 5. 环境变量

配置模板为 `backend/.env.example`。**必须先进入 `backend/` 目录再复制**：

```bat
cd backend
copy .env.example .env
```

原因：`app/core/config.py` 中的 `env_file=".env"` 是相对路径，相对**进程工作目录**解析；以本文档方式启动时工作目录即 `backend/`。放在仓库根目录的 `.env` 不会被读取。

关键变量：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/jd_platform.db` | 相对 `backend/` 解析 |
| `DATABASE_SYNC_URL` | `sqlite:///./data/jd_platform.db` | Alembic 等同步场景使用 |
| `LLM_DEFAULT_PROVIDER` | `mock` | 可选 `openai` / `anthropic` |
| `EMBEDDING_DIM` | `1024` | 向量维度 |
| `CRAWLER_ENABLED` | `true` | 关闭后禁用手动 URL 抓取 |
| `RESUME_STORAGE_DIR` | `./data/resumes` | 相对 `backend/` 解析 |
| `CORS_ORIGINS` | `["http://localhost:5173","http://localhost:3000"]` | 前端跨域白名单 |

---

## 6. 数据位置

| 内容 | 路径 |
|---|---|
| SQLite 数据库 | `backend/data/jd_platform.db` |
| 简历原文件 | `backend/data/resumes/` |

`backend/data/` 已被 `.gitignore` 忽略，不会进入版本管理。

---

## 7. 数据库迁移

```bat
cd backend
.venv\Scripts\alembic.exe upgrade head
```

当前迁移脚本只有一个：`alembic/versions/0001_init.py`（已改写为 SQLite 兼容）。

---

## 8. LLM 模式

- `mock`（默认）：离线可用，`structured_invoke` 返回带默认值的固定结构，`FakeEmbeddings` 提供 1024 维向量。
- `openai` / `anthropic`：需在 `backend/.env` 填入对应 API Key，真实接入仍走 LangChain。

---

## 9. 常用命令

```bat
REM 后端测试
cd backend
.venv\Scripts\python.exe -m pytest tests/ -v

REM 前端构建
cd frontend
npm run build

REM 前端类型检查
cd frontend
npx tsc --noEmit
```

---

## 10. 常见问题

### Q1: 后端启动报 `winerror 10048`

端口 8000 被占用。`start.bat` 会自动释放；手动启动时可先关闭占用进程，或改用其他端口。

### Q2: 修改了 `.env` 却不生效

确认文件位置是 `backend/.env` 而不是仓库根目录的 `.env`。根目录的那份不会被读取。

### Q3: 抓取 JD URL 失败

需要 Playwright Chromium。执行：

```bat
cd backend
.venv\Scripts\python.exe -m playwright install chromium
```

或设置 `CRAWLER_ENABLED=false` 关闭抓取功能。

### Q4: 还需要装 pgvector / zhparser / weasyprint 吗

不需要。这三项已随 Docker + PostgreSQL 方案一并移除：

- 向量检索 → 改为纯 Python 计算 cosine + Jaccard
- 中文全文检索 → 已移除
- PDF 导出 → 改用 reportlab，无系统字体依赖

### Q5: 定制化接口很慢

`POST /api/customizations` 已改为同步执行，本地约需数十秒。前端需使用长 loading 态并放宽超时。
