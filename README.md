# JD 定制化求职助手

> 基于 `interview-guide-master`（AGPL-3.0）二次裁剪。
> Python 单体后端 + 召回引擎，面向大数据挖掘后端岗位。

## 1. 项目特色

- **混合召回**：pgvector 向量召回 + PG 全文检索，0.6/0.4 加权融合
- **LLM 定制化**：差距分析 → 定制简历 → 押题（STAR 话术）6 步流水线
- **异步任务**：Celery + Redis + 状态机 + 乐观锁
- **多 Provider**：OpenAI / Anthropic / Mock，API Key Fernet 加密
- **零额外依赖**：向量库 + 关键词库都用 PG，单数据库部署

## 2. 目录结构

```
jd-resume-platform/
├── backend/           # FastAPI + SQLAlchemy 2.0 + Celery
├── frontend/          # React 18 + Vite + TS + Tailwind 3 + React Router 7
├── docs/              # 设计文档（design.md + 各模块）
├── scripts/           # init-postgres.sql（PG 扩展）
├── data/resumes/      # 简历文件存储（git ignore）
├── docker-compose.yml         # 完整部署（5 进程）
├── docker-compose.dev.yml     # 仅依赖（PG + Redis）
├── .env.example
└── README.md
```

## 3. 技术栈

**后端**：FastAPI 0.141 / SQLAlchemy 2.0 async / Pydantic v2 / Celery 5.6 / LangChain 0.3 / pgvector / weasyprint / playwright

**前端**：React 18.3 / Vite 5 / TypeScript 5.6 / Tailwind 3 / React Router 7

**基础设施**：PostgreSQL 16 + pgvector + zhparser，Redis 7

## 4. 快速开始（Docker Compose 一键起）

```bash
# 1. 准备环境变量
cp .env.example .env
# 至少填：POSTGRES_PASSWORD / FERNET_KEY
# 生成 Fernet key：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 2. 启动所有服务
docker compose up -d --build

# 3. 访问
# 前端:        http://localhost
# 后端 API:    http://localhost:8000
# API 文档:    http://localhost:8000/docs
```

## 5. 本地开发（推荐）

只起依赖，后端用 venv 跑、前端用 npm 跑，方便改代码热重载。

```bash
# 1. 起依赖
docker compose -f docker-compose.dev.yml up -d

# 2. 后端
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows
# source .venv/bin/activate    # Linux/Mac
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 3. 另起一个 shell：Celery worker
celery -A app.tasks.celery_app worker -l info

# 4. 另起一个 shell：前端
cd ../frontend
npm install
npm run dev   # http://localhost:5173
```

## 6. 演示路径

1. **模型管理** → 新增 LLM Provider（API Key 必填）并设为默认
2. **简历** → 上传一份 PDF/DOCX/TXT → 等待 `parse_status: COMPLETED`
3. **JD** → 粘贴文本 或 提交牛客/Boss URL → 等待 `crawl_status: COMPLETED`
4. **定制化** → 选 (JD, 简历) + 押题数 → 发起任务 → 轮询到 `COMPLETED`
5. 详情页查看 4 块报告：差距分析 / 定制简历 / 押题 / 召回指标
6. **导出 PDF** → 一键下载中文不乱码的 PDF 报告

## 7. 测试

```bash
# 后端（55 个测试）
cd backend
.\.venv\Scripts\python.exe -m pytest tests/ -v

# 前端类型检查
cd frontend
npm run typecheck

# 前端构建
npm run build
```

## 8. 端到端 REST API

完整 API 列表（HTTP 200，code 区分成功失败）：

| 模块 | 端点 |
|---|---|
| 健康 | `GET /health` |
| 简历 | `POST/GET/DELETE /api/resumes`、`/{id}/reparse`、`/{id}/status`、`/{id}/file` |
| JD | `POST /api/jds/{text,url}`、`GET/DELETE /api/jds`、`/{id}/status` |
| 定制化 | `POST/GET/DELETE /api/customizations`、`/{id}/status`、`/{id}/retry`、`/{id}/pdf` |
| 模型 | `GET/POST/PUT/DELETE /api/llm-providers`、`/{id}/{set-default,test}` |

访问 `http://localhost:8000/docs` 看 FastAPI 自动生成的 Swagger。

## 9. 关键设计点（面试讲点）

1. **混合召回原理**：向量 0.6 + 关键词 0.4，归一化后加权融合
2. **为什么用 PG 不上 ES**：单数据库，简历库 < 1000，零额外依赖
3. **Celery 状态机 + 乐观锁**：抢任务时 `UPDATE ... WHERE status='PENDING'`，rowcount=0 说明被抢走
4. **统一 Result 响应**：所有接口 HTTP 200，前端按 `code` 区分
5. **API Key 加密**：Fernet 对称加密 + 脱敏（首尾 4 位）
6. **异步流水线**：上传 → 解析 → 索引 → 定制 全部异步，前端轮询

## 10. 已知限制

- **Windows PDF 导出**：weasyprint 缺 GTK 原生库，需要先装 MSYS2/Pango 才能用 `/pdf` 端点
- **zhparser 扩展**：基础 pgvector 镜像未必带；如果 `CREATE EXTENSION` 失败会自动 fallback 到 `simple` 词典（中文按字切，效果差但能跑）
- **爬虫反爬**：牛客/Boss 经常触发验证码，抓取失败时手动粘贴 JD 文本兜底
- **Embedding 维度**：固定 1024（与 design.md §4 一致），切换 Embedding 模型时需要重建所有向量

## 11. License

按 interview-guide-master（AGPL-3.0）协议开源，个人学习/求职项目不发布可豁免。
