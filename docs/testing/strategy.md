# 测试策略

> 当前为本地优先方案：pytest + SQLite 内存库，纯逻辑单元测试为主。
> 不依赖 PostgreSQL / Redis / Celery / Testcontainers。

---

## 1. 现状概览

- 测试目录：`backend/tests/`
- 运行方式：

```bat
cd backend
.venv\Scripts\python.exe -m pytest tests/ -v
```

- 全部测试均不需要外部服务：数据库用 `sqlite+aiosqlite:///:memory:`，LLM 用 mock provider。
- `tests/conftest.py` 在 import `app.*` 之前设置环境变量（`DATABASE_URL`、`LLM_DEFAULT_PROVIDER=mock`、`EMBEDDING_DIM=1024`）。

---

## 2. 测试分层

| 层级 | 工具 | 覆盖范围 | 状态 |
|---|---|---|---|
| 单元测试 | pytest + pytest-asyncio | Service 业务逻辑、Util、Prompt 渲染、Schema 校验、异常转换 | 已落地 |
| 集成测试 | pytest + httpx | API + DB 端到端 | 未落地 |
| E2E 测试 | pytest + Playwright | 完整业务流程 | 未落地 |

---

## 3. 现有测试文件

| 文件 | 覆盖内容 |
|---|---|
| `test_crawler_factory.py` | URL → source 识别（爬虫工厂纯逻辑） |
| `test_schemas.py` | 通用 Pydantic schema 校验 |
| `test_customization_schemas.py` | 定制化相关 schema 校验 |
| `test_exceptions.py` | 业务异常 → `Result.fail` 转换 |
| `test_prompts.py` | Prompt 模板渲染 |
| `test_evaluation.py` | 召回评估指标（recall / precision / ndcg） |
| `test_retrieval_normalize.py` | 检索分数归一化 |
| `test_llm_services.py` | LLMService（以 MagicMock 替换真实调用） |
| `test_security.py` | Fernet 加解密 |
| `conftest.py` | 测试环境变量与公共 fixture |

---

## 4. 覆盖率要求（目标值）

| 模块 | 最低覆盖率 |
|---|---|
| 召回引擎（retrieval_service） | 90% |
| 评估指标（evaluation_service） | 90% |
| 差距分析（gap_analysis_service） | 85% |
| 定制简历（customize_service） | 85% |
| 押题（predict_service） | 85% |
| LLM 服务（llm_service） | 85% |
| 其他 Service | 80% |
| API 路由 | 70% |

---

## 5. pytest 配置

实际配置位于 `backend/pytest.ini`：

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
addopts = -v
```

---

## 6. Mock 策略

### 6.1 Mock LLM

`LLM_DEFAULT_PROVIDER=mock` 时，`structured_invoke` 返回带 `default_factory` 默认值的固定结构；
`match_score` 等必填字段返回 `0`，以通过 Pydantic 校验。

单元测试中也可直接以 `AsyncMock(spec=LLMService)` 替换：

```python
service = AsyncMock(spec=LLMService)
service.structured_invoke.return_value = JdStructured(
    company="测试公司",
    position="Java 开发",
    salary_min=20,
    salary_max=30,
    city="北京",
    skills=["Java", "Spring"],
)
```

### 6.2 Mock Playwright

```python
with patch("playwright.async_api.async_playwright") as mock:
    browser = AsyncMock()
    page = AsyncMock()
    page.inner_text.return_value = "测试 JD 内容"
    browser.new_page.return_value = page
    mock.return_value.__aenter__.return_value.chromium.launch.return_value = browser
    yield mock
```

### 6.3 测试数据库

使用 SQLite 内存库，无需容器：

```python
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_SYNC_URL", "sqlite:///:memory:")
```

---

## 7. 已移除的测试依赖

以下依赖随 Docker / Celery 方案一并移除，**不要在新的测试中引用**：

- `testcontainers`（曾用于拉起真实 PostgreSQL）
- `celery` 的 `task_always_eager` 模式
- `faker` / `freezegun`（未实际使用）

若将来需要集成测试，应改为 SQLite 内存库 + `httpx.ASGITransport`，不要重新引入容器依赖。

---

## 8. CI 集成

```yaml
name: Tests
on: [push, pull_request]
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with:
      python-version: '3.12'
  - run: pip install -r backend/requirements.txt
  - run: cd backend && pytest --cov=app --cov-report=xml --cov-fail-under=80
```

---

## 9. 面试讲点

1. **"测试覆盖率怎么保证？"**
   > pytest-cov + CI 卡线（核心模块 ≥ 85%，算法 ≥ 90%）。每次 PR 必须通过覆盖率检查。

2. **"LLM 调用怎么测？"**
   > Mock LLMService，业务逻辑用固定返回验证。Prompt 模板单独测渲染正确性。
   > 项目内置 mock provider，可在无 API Key 的离线环境下跑通完整链路。

3. **"为什么不用 Testcontainers 起真实数据库？"**
   > 早期用 PostgreSQL + pgvector 时确实如此。后来为降低本地运行门槛改为 SQLite，
   > 测试也随之简化为内存库——代价是不再覆盖 PG 特有语法，收益是零外部依赖、秒级启动。

4. **"异步任务怎么测？"**
   > 现在没有异步任务了。定制化流程改为同步执行，测试直接 `await` 调用结果即可。
