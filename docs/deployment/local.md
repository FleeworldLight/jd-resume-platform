# 本地部署

> Docker Compose 一键启动全部依赖 + 应用。

---

## 1. 环境要求

| 依赖 | 版本 | 必需 | 说明 |
|---|---|---|---|
| Docker | 20+ | ✅ | 容器运行时 |
| Docker Compose | 2+ | ✅ | 编排工具 |
| Python | 3.12+ | ⚠️ | 本地开发时需要 |
| Poetry | 1.8+ | ⚠️ | 本地开发时需要 |
| Node.js | 18+ | ⚠️ | 前端开发时需要 |
| pnpm | 10+ | ⚠️ | 前端推荐 |

---

## 2. 目录结构

```
jd-resume-platform/
├── backend/                    # Python 后端
├── frontend/                   # React 前端
├── docs/                       # 设计文档
├── docker-compose.yml          # 全部编排
├── docker-compose.dev.yml      # 仅依赖（开发用）
├── .env.example                # 环境变量示例
├── README.md
└── data/                       # 简历文件（git ignore）
```

---

## 3. 快速启动

### 3.1 克隆 + 配置

```bash
git clone <repo-url>
cd jd-resume-platform

# 复制环境变量
cp .env.example .env

# 编辑 .env，至少填：
# - LLM_API_KEY（必需）
# - LLM_ENCRYPTION_KEY（必需）
# - POSTGRES_PASSWORD（必需）
```

### 3.2 启动依赖（仅数据库 + Redis）

```bash
docker compose -f docker-compose.dev.yml up -d
```

启动 PostgreSQL（含 pgvector + zhparser） + Redis。

### 3.3 本地启动后端

```bash
cd backend
poetry install
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload --port 8000

# 另开一个终端：Celery worker
poetry run celery -A app.tasks.celery_app worker -l info
```

### 3.4 本地启动前端

```bash
cd frontend
pnpm install
pnpm dev
```

访问 `http://localhost:5173`。

### 3.5 一键启动全部（Docker Compose）

```bash
docker compose up -d --build
```

启动：
- PostgreSQL + Redis + 后端 + Celery worker + 前端

访问：
- 前端：`http://localhost`
- 后端 API：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

---

## 4. docker-compose.yml

### 4.1 开发版（仅依赖）

```yaml
# docker-compose.dev.yml
services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: jd-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: jd_platform
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-password}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./scripts/init-postgres.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
  
  redis:
    image: redis:7-alpine
    container_name: jd-redis
    restart: unless-stopped
    ports:
      - "${REDIS_PORT:-6379}:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
```

### 4.2 完整版

```yaml
# docker-compose.yml
services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: jd-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: jd_platform
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-password}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./scripts/init-postgres.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
  
  redis:
    image: redis:7-alpine
    container_name: jd-redis
    restart: unless-stopped
    ports:
      - "${REDIS_PORT:-6379}:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
  
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: jd-backend
    restart: unless-stopped
    ports:
      - "${BACKEND_PORT:-8000}:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - resume_files:/app/data/resumes
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:${POSTGRES_PASSWORD:-password}@postgres:5432/jd_platform
      REDIS_URL: redis://redis:6379/0
      RESUME_STORAGE_DIR: /app/data/resumes
  
  celery-worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: jd-celery-worker
    restart: unless-stopped
    command: celery -A app.tasks.celery_app worker -l info
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - resume_files:/app/data/resumes
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:${POSTGRES_PASSWORD:-password}@postgres:5432/jd_platform
      REDIS_URL: redis://redis:6379/0
      RESUME_STORAGE_DIR: /app/data/resumes
  
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: jd-frontend
    restart: unless-stopped
    ports:
      - "${FRONTEND_PORT:-80}:80"
    depends_on:
      - backend

volumes:
  pgdata:
  resume_files:
```

---

## 5. .env.example

```env
# ===================
# 数据库
# ===================
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=jd_platform
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password

# ===================
# Redis
# ===================
REDIS_HOST=localhost
REDIS_PORT=6379

# ===================
# 后端
# ===================
BACKEND_PORT=8000
RESUME_STORAGE_DIR=./data/resumes
APP_ENV=development

# ===================
# LLM
# ===================
# 至少填一个 LLM_API_KEY
LLM_API_KEY=your-dashscope-api-key
LLM_MODEL=qwen3.5-flash
LLM_EMBEDDING_MODEL=text-embedding-v3
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# API Key 加密密钥（Fernet）
# 生成：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
LLM_ENCRYPTION_KEY=your-generated-fernet-key=

# ===================
# 爬虫
# ===================
JD_CRAWLER_ENABLED=true
JD_CRAWLER_TIMEOUT=60
JD_CRAWLER_USER_AGENT_POOL=app/crawler/user_agents.yml

# ===================
# 召回
# ===================
RETRIEVAL_VECTOR_WEIGHT=0.6
RETRIEVAL_KEYWORD_WEIGHT=0.4
RETRIEVAL_CANDIDATE_TOP_K=100
RETRIEVAL_FINAL_TOP_K=50

# ===================
# 定制化
# ===================
CUSTOMIZATION_PREDICT_QUESTION_COUNT=5
CUSTOMIZATION_RETRY_MAX=2
```

---

## 6. 后端 Dockerfile

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# 系统依赖（Playwright + weasyprint）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libpango-1.0-0 libpangoft2-1.0-0 \
    curl wget \
    && rm -rf /var/lib/apt/lists/*

# Poetry
ENV POETRY_HOME=/opt/poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="${PATH}:${POETRY_HOME}/bin"

# 依赖
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction

# Playwright 浏览器
RUN playwright install chromium
RUN playwright install-deps chromium

# 代码
COPY . .

# 数据目录
RUN mkdir -p /app/data/resumes

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 7. 前端 Dockerfile

```dockerfile
# frontend/Dockerfile
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# Nginx 镜像
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

```nginx
# frontend/nginx.conf
server {
    listen 80;
    server_name _;
    
    root /usr/share/nginx/html;
    index index.html;
    
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

---

## 8. 数据库初始化

**`scripts/init-postgres.sql`**

```sql
-- 启用 pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- 启用 zhparser（中文分词）
CREATE EXTENSION IF NOT EXISTS zhparser;

-- 中文全文检索配置
CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser);
ALTER TEXT SEARCH CONFIGURATION chinese
    ADD MAPPING FOR n, v, a, i, e, l, t WITH simple;
```

**Alembic 迁移**

```bash
# 生成迁移
alembic revision --autogenerate -m "init schema"

# 应用迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

---

## 9. 常用运维命令

```bash
# 查看日志
docker compose logs -f backend
docker compose logs -f celery-worker

# 进入容器
docker compose exec backend bash
docker compose exec postgres psql -U postgres -d jd_platform

# 重建服务
docker compose up -d --build backend

# 停止
docker compose down

# 清理数据（慎用）
docker compose down -v
```

---

## 10. 健康检查

```bash
# 后端
curl http://localhost:8000/health

# 数据库
docker compose exec postgres pg_isready

# Redis
docker compose exec redis redis-cli ping
```

---

## 11. 常见问题

### Q1: 启动时 zhparser 扩展安装失败？

**原因**：基础镜像没有 zhparser。

**解决**：使用 `pgvector/pgvector:pg16` 基础镜像，然后手动安装：
```bash
docker compose exec postgres apt-get update
docker compose exec postgres apt-get install -y postgresql-16-zhparser
docker compose exec postgres psql -U postgres -c "CREATE EXTENSION zhparser;"
```

### Q2: Playwright 浏览器启动失败？

**原因**：缺少系统依赖。

**解决**：确保 Dockerfile 里安装了 `playwright install-deps`。

### Q3: weasyprint 中文显示乱码？

**解决**：安装中文字体：
```dockerfile
RUN apt-get install -y fonts-noto-cjk
```

### Q4: Alembic 找不到模型？

**检查** `alembic/env.py`：
```python
from app.db.base import Base
from app.db.models import *  # 显式导入
target_metadata = Base.metadata
```