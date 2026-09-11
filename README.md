# JD Resume Platform

这是一个本地优先的简历定制平台：后端用 FastAPI + SQLite，LLM 默认走 mock provider，前端直接用 Vite 启动，不依赖 Docker、Redis、Celery、Postgres 或外部服务。

## 1. 目标

- Windows 本地双击打开即可运行
- 默认使用 SQLite，本地数据文件保存在 `data/jd_platform.db`
- 默认启用爬虫，但可通过 `CRAWLER_ENABLED=false` 关闭
- 默认 LLM provider 为 `mock`，离线可用
- 保留 LangChain（OpenAI / Anthropic 真实接入仍可用）

## 2. 目录说明

- `backend/`：FastAPI 后端
- `frontend/`：React + Vite 前端
- `data/`：数据库和简历存储目录
- `start.bat`：Windows 双击启动脚本
- `.env.example`：环境变量示例

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

复制示例：

```bat
copy .env.example .env
```

默认示例已切换成 SQLite：

```env
DATABASE_URL=sqlite+aiosqlite:///./data/jd_platform.db
DATABASE_SYNC_URL=sqlite:///./data/jd_platform.db
LLM_DEFAULT_PROVIDER=mock
CRAWLER_ENABLED=true
```

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
data/jd_platform.db
```

简历原文件默认目录：

```text
data/resumes/
```

## 8. LLM 模式

默认模式为 `mock`，无需 OpenAI / Anthropic Key 即可本地运行。

如果要接真实模型，可在 `LLM_DEFAULT_PROVIDER` 里切成 `openai` 或 `anthropic`，并填写对应 API Key。

## 9. 说明

- 当前版本已去掉 Docker / Redis / Celery / PostgreSQL 依赖
- 爬虫保留并默认启用，适合本地抓取 JD
- API 仍兼容统一 `Result` 响应格式，前后端交互保持一致
