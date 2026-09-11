# JD 定制化求职助手 - 总设计文档

> **文档状态：部分过时（2026-09-11 标注）**
>
> 本文写于项目采用 Docker + PostgreSQL + pgvector + Redis + Celery 架构的阶段。
> 当前实际架构已简化为 SQLite + mock LLM provider + 无 Celery 的同步执行，详见根目录 README.md。
> 下文涉及 Docker / Postgres / pgvector / Redis / Celery / weasyprint 的段落仅作历史设计参考，不代表现状。

> 基于 interview-guide-master（AGPL-3.0）二次裁剪。
> 目标：Python 单体后端 + 召回引擎，面向大数据挖掘后端岗位。

---

## 1. 项目定位

**痛点**：求职者拿到 JD 后，传统做法靠经验手动改简历、押题，效率低且命中率不稳。

**目标**：用户粘贴 JD 文本或提交牛客/Boss URL，系统自动完成：
1. JD 结构化抽取
2. pgvector 向量召回 + PG 全文检索关键词精排，混合打分
3. 差距分析
4. 定制版简历生成
5. 面试高频题 + STAR 话术

**目标用户**：求职者本人（单租户、个人使用）。

**非目标**：模拟面试、语音面试、多租户、真实投递、RAG 题库。

---

## 2. 架构总览

```
┌────────────────────────────────────────────┐
│  Frontend (React 18 + Vite + Tailwind + TS) │
└────────────────┬───────────────────────────┘
                 │ HTTP
┌────────────────▼───────────────────────────┐
│  Python 后端 (FastAPI)                       │
│  ├─ API 层：路由 + 校验 + 限流              │
│  ├─ Service 层：业务编排                    │
│  ├─ Repository 层：SQLAlchemy 2.0 async    │
│  ├─ LLM 层：LangChain + Pydantic            │
│  ├─ Crawler 层：Playwright                 │
│  ├─ Task 层：Celery                        │
│  └─ 召回引擎：pgvector + PG tsvector        │
└────────┬───────────────────────────┬───────┘
         │ SQL                       │ Broker
┌────────▼──────────┐       ┌────────▼────────┐
│  PostgreSQL + pgvector │       │  Redis           │
│  本地存储简历文件         │       └─────────────────┘
└───────────────────┘
```

**5 个进程**：PostgreSQL / Redis / Python API / Celery Worker / Frontend。

---

## 3. 技术栈

| 技术 | 版本 | 用途 |
|---|---|---|
| Python | 3.12+ | 主语言 |
| FastAPI | 0.115+ | Web 框架 |
| SQLAlchemy | 2.0 (async) | ORM |
| Alembic | 1.13+ | 数据库迁移 |
| Pydantic | v2 | 数据模型 + 验证 |
| Celery | 5.4+ | 异步任务 |
| Redis | 7 | Celery broker + 缓存 |
| LangChain | 0.7+ | LLM 编排 |
| Playwright | 1.48+ | 爬虫（牛客/Boss）|
| weasyprint | 63+ | PDF 导出 |
| httpx | 0.27+ | 异步 HTTP |
| tenacity | 9+ | 重试 |
| structlog | 24+ | 结构化日志 |
| pgvector (Python) | 0.3+ | 向量检索 |
| scipy / numpy | - | 评估算法 |
| pytest | 8+ | 测试 |
| Poetry | - | 依赖管理 |

**前端**：React 18 + Vite + Tailwind 4 + TypeScript 5.6 + React Router 7。

**基础设施**：PostgreSQL 16 (含 pgvector 扩展) + Redis 7。

---

## 4. 数据模型

```sql
-- 简历
CREATE TABLE resumes (
    id              BIGSERIAL PRIMARY KEY,
    original_filename VARCHAR(255) NOT NULL,
    storage_path    VARCHAR(512),       -- 本地路径
    resume_text     TEXT,
    content_hash    VARCHAR(64) UNIQUE, -- SHA-256 去重
    parse_status    VARCHAR(32) DEFAULT 'PENDING',  -- PENDING/PROCESSING/COMPLETED/FAILED
    parse_error     TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- JD
CREATE TABLE jds (
    id              BIGSERIAL PRIMARY KEY,
    source          VARCHAR(32) NOT NULL,  -- NOWCODER / BOSS / MANUAL
    source_url      TEXT,
    raw_text        TEXT NOT NULL,
    company         VARCHAR(128),
    position        VARCHAR(128),
    salary_min      INT,
    salary_max      INT,
    city            VARCHAR(128),
    experience      VARCHAR(64),
    education       VARCHAR(64),
    skills          JSONB,
    responsibilities JSONB,
    requirements    JSONB,
    structured      JSONB,                 -- 完整结构化结果
    crawl_status    VARCHAR(32) DEFAULT 'PENDING',  -- PENDING/PROCESSING/COMPLETED/FAILED
    crawl_error     TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- 定制化任务
CREATE TABLE customizations (
    id                BIGSERIAL PRIMARY KEY,
    jd_id             BIGINT NOT NULL REFERENCES jds(id),
    base_resume_id    BIGINT NOT NULL REFERENCES resumes(id),
    status            VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    error_message     TEXT,
    retry_count       INT DEFAULT 0,
    gap_report        JSONB,
    customized_resume JSONB,
    prediction        JSONB,
    retrieval_metrics JSONB,
    matched_resumes   JSONB,
    provider_used     VARCHAR(64),
    started_at        TIMESTAMPTZ,
    completed_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now()
);

-- 简历向量（召回引擎用）
CREATE TABLE resume_vectors (
    id            BIGSERIAL PRIMARY KEY,
    resume_id     BIGINT UNIQUE NOT NULL,
    embedding     vector(1024),
    search_tsv    tsvector,         -- PG 全文检索
    keywords      JSONB,
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_resume_vectors_embedding ON resume_vectors USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_resume_vectors_search ON resume_vectors USING GIN (search_tsv);

-- 评估日志
CREATE TABLE evaluation_logs (
    id              BIGSERIAL PRIMARY KEY,
    customization_id BIGINT,
    strategy        VARCHAR(32),   -- VECTOR / KEYWORD / HYBRID
    metrics         JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- LLM Provider
CREATE TABLE llm_providers (
    id                BIGSERIAL PRIMARY KEY,
    name              VARCHAR(64) UNIQUE NOT NULL,
    provider_type     VARCHAR(32) NOT NULL,
    base_url          VARCHAR(512),
    api_key_encrypted TEXT,
    chat_model        VARCHAR(128),
    embedding_model   VARCHAR(128),
    is_default        BOOLEAN DEFAULT false,
    enabled           BOOLEAN DEFAULT true,
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now()
);
```

---

## 5. 目录结构

```
jd-resume-platform/
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── exceptions.py
│   │   │   ├── result.py
│   │   │   ├── rate_limit.py
│   │   │   ├── logging.py
│   │   │   └── security.py
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   ├── resumes.py
│   │   │   ├── jds.py
│   │   │   ├── customizations.py
│   │   │   └── llm_providers.py
│   │   ├── services/
│   │   │   ├── resume_service.py
│   │   │   ├── jd_service.py
│   │   │   ├── crawler_service.py
│   │   │   ├── llm_service.py
│   │   │   ├── gap_analysis_service.py
│   │   │   ├── customize_service.py
│   │   │   ├── predict_service.py
│   │   │   ├── retrieval_service.py
│   │   │   └── evaluation_service.py
│   │   ├── tasks/
│   │   │   ├── celery_app.py
│   │   │   ├── resume_tasks.py
│   │   │   ├── jd_tasks.py
│   │   │   └── customization_tasks.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   └── models/
│   │   ├── schemas/
│   │   ├── prompts/
│   │   ├── crawler/
│   │   │   ├── strategies/
│   │   │   └── user_agents.yml
│   │   └── utils/
│   └── tests/
├── frontend/
│   ├── package.json
│   └── src/
├── data/                       # 简历文件本地存储（git ignore）
│   └── resumes/
├── docs/                       # 设计文档
│   ├── design.md               # 总览（本文档）
│   ├── architecture/
│   ├── modules/
│   ├── testing/
│   └── deployment/
├── docker-compose.yml
├── .env.example
└── README.md
```

详细设计见子文档：
- [`docs/architecture/retrieval.md`](architecture/retrieval.md) — 召回引擎设计
- [`docs/architecture/llm.md`](architecture/llm.md) — LLM 调用规范
- [`docs/architecture/async-tasks.md`](architecture/async-tasks.md) — 异步任务设计
- [`docs/architecture/error-handling.md`](architecture/error-handling.md) — 异常与统一响应
- [`docs/modules/resume.md`](modules/resume.md) — 简历模块
- [`docs/modules/jd.md`](modules/jd.md) — JD 模块
- [`docs/modules/customization.md`](modules/customization.md) — 定制化模块
- [`docs/modules/llm-provider.md`](modules/llm-provider.md) — 模型管理模块
- [`docs/testing/strategy.md`](testing/strategy.md) — 测试策略
- [`docs/testing/test-cases.md`](testing/test-cases.md) — 测试用例清单
- [`docs/deployment/local.md`](deployment/local.md) — 本地部署
- [`docs/deployment/acceptance.md`](deployment/acceptance.md) — 验收标准

---

## 6. 核心模块设计（概要）

### 6.1 LLM Service（统一 LLM 调用入口）

封装 LangChain + 多 Provider + 结构化输出 + 重试降级。

```python
class LLMService:
    async def get_chat_model(self, provider_name: str | None = None) -> BaseChatModel: ...
    async def structured_invoke[T](
        self,
        prompt_template: ChatPromptTemplate,
        input_vars: dict,
        output_schema: type[T],
        provider_name: str | None = None,
        max_retries: int = 3,
    ) -> T: ...
```

详见 [`docs/architecture/llm.md`](architecture/llm.md)。

### 6.2 召回引擎（pgvector + PG 全文检索）

```python
class RetrievalService:
    async def index_resume(self, resume_id: int, text: str): ...
    async def vector_search(self, query: str, top_k: int) -> list[ResumeScore]: ...
    async def keyword_search(self, query: str, top_k: int) -> list[ResumeScore]: ...
    async def hybrid_search(self, query: str, top_k: int) -> list[ResumeScore]: ...
```

混合打分：`final_score = 0.6 * vector_score + 0.4 * keyword_score`

详见 [`docs/architecture/retrieval.md`](architecture/retrieval.md)。

### 6.3 异步任务（Celery）

定制化主任务为 DAG：

```
customize_resume_task
  ├─ 1. 召回（同步，pgvector + PG tsvector）
  ├─ 2. 差距分析（LLM）
  ├─ 3. 定制简历（LLM）
  ├─ 4. 押题（LLM）
  └─ 5. 落库
```

详见 [`docs/architecture/async-tasks.md`](architecture/async-tasks.md)。

### 6.4 爬虫（Playwright 策略模式）

支持来源：
- ✅ 牛客（`nowcoder`）
- ✅ Boss 直聘（`zhipin` / `boss`）
- ❌ 其他网站（明确拒绝，提示粘贴）

```python
class JdCrawler(Protocol):
    async def crawl(self, url: str) -> CrawlResult: ...

class CrawlerService:
    def get_crawler(self, url: str) -> JdCrawler:
        if "nowcoder" in url: return NowcoderCrawler()
        elif "zhipin" in url or "boss" in url: return BossCrawler()
        else: raise BusinessException(UNSUPPORTED_JD_SOURCE)
```

### 6.5 评估指标

```python
class EvaluationService:
    def recall_at_k(self, results: list[int], ground_truth: set[int], k: int) -> float: ...
    def precision_at_k(self, results: list[int], ground_truth: set[int], k: int) -> float: ...
    def ndcg_at_k(self, results: list[ResumeScore], ground_truth: set[int], k: int) -> float: ...
    def evaluate(self, results, ground_truth) -> EvalResult: ...
```

---

## 7. REST API

```
# 简历
POST   /api/resumes                    # 上传简历
GET    /api/resumes                    # 列表
GET    /api/resumes/{id}               # 详情
DELETE /api/resumes/{id}
POST   /api/resumes/{id}/reparse
GET    /api/resumes/{id}/status        # 轮询解析状态
GET    /api/resumes/{id}/file          # 下载原文件

# JD
POST   /api/jds/text                   # 粘贴 JD 文本（兜底）
POST   /api/jds/url                    # 提交牛客/Boss URL
GET    /api/jds
GET    /api/jds/{id}
DELETE /api/jds/{id}
GET    /api/jds/{id}/status            # 抓取/解析状态

# 定制化
POST   /api/customizations             # 发起定制化
GET    /api/customizations
GET    /api/customizations/{id}
GET    /api/customizations/{id}/status
DELETE /api/customizations/{id}
POST   /api/customizations/{id}/retry
GET    /api/customizations/{id}/pdf    # 导出 PDF

# 模型管理
GET    /api/llm-providers
POST   /api/llm-providers
PUT    /api/llm-providers/{id}
DELETE /api/llm-providers/{id}
POST   /api/llm-providers/{id}/test
```

---

## 8. 端到端流程

### 8.1 定制化主流程

```
1. 用户上传基础简历
   POST /api/resumes
   → Celery: parse_resume_task（异步解析文本）
   → Celery: index_resume_task（向量化 + 建索引）

2. 用户提交 JD（粘贴文本 / URL）
   POST /api/jds/text 或 /api/jds/url
   → LLM 结构化抽取（粘贴模式同步，URL 模式异步）

3. 用户发起定制化
   POST /api/customizations { jd_id, resume_id }
   → Celery: customize_resume_task
       ├─ a. 召回（pgvector + PG tsvector，混合打分）
       ├─ b. 差距分析（LLM）
       ├─ c. 定制简历（LLM）
       ├─ d. 押题（LLM）
       └─ e. 落库 + 状态置 COMPLETED

4. 前端轮询
   GET /api/customizations/{id}/status
   → COMPLETED 后展示报告 / 导出 PDF
```

### 8.2 JD URL 抓取流程

```
1. 用户提交 URL
   POST /api/jds/url { url }
   → 校验来源（必须含 nowcoder / zhipin / boss）
   → Celery: crawl_jd_task
       ├─ a. 选爬虫策略
       ├─ b. Playwright 渲染 → 拿 innerText
       ├─ c. 存 raw_text → crawl_status=PARSED
       └─ d. 异步 LLM 结构化 → crawl_status=STRUCTURED

2. 前端轮询状态
```

---

## 9. 关键设计点

### 9.1 统一规范

- **统一响应**：`Result<T>(code, message, data)`，所有接口 HTTP 200
- **统一异常**：`BusinessException(ErrorCode, "描述")` + 全局异常处理器
- **统一 LLM**：所有调用走 `LLMService.structured_invoke()`
- **统一重试**：外部调用必须用 `tenacity` 装饰器
- **统一日志**：`structlog`，含 trace_id

### 9.2 限流

爬虫接口 2 QPS、LLM 接口 5 QPS，实现用 Redis 滑动窗口（`slowapi` 或自研中间件）。

### 9.3 Prompt 管理

- 全部外置到 `app/prompts/*.py`，每个文件导出 `ChatPromptTemplate`
- 不允许字符串拼接 Prompt
- 版本化：`jd_extract_v1.py`

### 9.4 反爬

- 单 IP 2 QPS 限流
- UA 池轮换（`user_agents.yml` 50 条）
- 失败指数退避（1s/2s/4s）
- 同 URL Redis 分布式锁去重
- 不持久化登录态
- 仅支持牛客、Boss，其他来源拒绝

### 9.5 配置

- `.env` + `pydantic-settings`
- 敏感信息加密（API Key 用 Fernet 对称加密）
- 运行时配置可写回 `~/.jd-platform/llm-providers.yml`

---

## 10. 部署

详见 [`docs/deployment/local.md`](deployment/local.md)。

```yaml
# docker-compose.yml（精简版）
services:
  postgres:
    image: pgvector/pgvector:pg16
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
    environment:
      POSTGRES_PASSWORD: password
  
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
  
  backend:
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [postgres, redis]
    volumes:
      - resume_files:/app/data/resumes
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:password@postgres:5432/jd_platform
      REDIS_URL: redis://redis:6379/0
      RESUME_STORAGE_DIR: /app/data/resumes
  
  celery-worker:
    build: ./backend
    command: celery -A app.tasks.celery_app worker -l info
    depends_on: [redis, postgres, backend]
    volumes:
      - resume_files:/app/data/resumes
  
  frontend:
    build: ./frontend
    ports: ["80:80"]

volumes:
  pgdata:
  resume_files:
```

---

## 11. 测试 + 验收

详见：
- [`docs/testing/strategy.md`](testing/strategy.md) — 测试策略
- [`docs/testing/test-cases.md`](testing/test-cases.md) — 测试用例清单
- [`docs/deployment/acceptance.md`](deployment/acceptance.md) — 验收标准

**测试层级**：
- 单元测试：Service / Util / Prompt 模板渲染
- 集成测试：API + 数据库 + Celery（eager 模式）
- 端到端测试：完整流程（上传 → 抓 JD → 定制 → 报告）

**覆盖率要求**：
- 核心 Service ≥ **85%**
- 召回/评估算法 ≥ **90%**

---

## 12. 上线检查清单

```
□ Alembic V1 初始化所有表
□ pgvector + zhparser 扩展安装
□ LLM API Key 跑通一次端到端
□ Celery worker 注册成功
□ 限流配置生效
□ 日志脱敏（API Key、JD 原文超 200 字符截断）
□ Docker Compose 一键启动测试
□ README 完整：环境变量、启动、演示路径
```

---

## 13. 后续可选增强

- [ ] 简历模板选择（按行业）
- [ ] 押题命中率反馈
- [ ] 历史定制化对比
- [ ] 多 JD 横向对比
- [ ] 简历-JD 关键词云可视化
- [ ] Celery Flower + Prometheus 监控

---

## 14. 风险与不做

**不做**：模拟面试、语音面试、多租户、真实投递、登录注册。

**法律风险**：
- 牛客 / Boss 抓取仅个人求职使用，不商用
- 抓取失败时可手动粘贴 JD 兜底

**AGPL 风险**：复用 interview-guide-master 的设计思路与部分代码（按 AGPL-3.0 协议开源），个人学习/求职项目不发布可豁免。

---

## 15. 周计划

| 周 | 任务 | 交付物 |
|---|---|---|
| W1 | Python 后端骨架 + FastAPI + Alembic + Docker | hello world |
| W2 | 简历 CRUD + JD（粘贴 + URL 抓取） + 结构化抽取 | 简历/JD 端到端 |
| W3 | 召回引擎 + 定制化流水线 + 评估指标 | 完整定制化跑通 |
| W4 | 前端 React + PDF 导出 + 测试 + README | 可演示完整流程 |

**4 周交付**。