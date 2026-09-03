# 测试策略

> pytest 全覆盖，分单元 / 集成 / E2E 三层。

---

## 1. 测试金字塔

```
       E2E（少）
      ━━━━━━━━
     集成（适量）
    ━━━━━━━━━━━━
   单元（多，覆盖广）
  ━━━━━━━━━━━━━━━━━━━
```

---

## 2. 测试层级

| 层级 | 工具 | 覆盖范围 | 数量 |
|---|---|---|---|
| 单元测试 | pytest + pytest-asyncio | Service 业务、Util、Prompt 渲染 | 多 |
| 集成测试 | pytest + httpx + Testcontainers | API + DB + Celery | 中 |
| E2E 测试 | pytest + Playwright | 完整流程 | 少 |

---

## 3. 覆盖率要求

| 模块 | 最低覆盖率 |
|---|---|
| 召回引擎（retrieval_service） | **90%** |
| 评估指标（evaluation_service） | **90%** |
| 差距分析（gap_analysis_service） | 85% |
| 定制简历（customize_service） | 85% |
| 押题（predict_service） | 85% |
| LLM 服务（llm_service） | 85% |
| 其他 Service | 80% |
| API 路由 | 70% |

---

## 4. 工具与配置

### 4.1 依赖

```toml
# pyproject.toml
[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-asyncio = "^0.23"
pytest-cov = "^5.0"
httpx = "^0.27"
testcontainers = "^4.7"
faker = "^25.0"
freezegun = "^1.4"
```

### 4.2 pytest.ini

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-v --strict-markers --tb=short"
markers = [
    "unit: 单元测试",
    "integration: 集成测试",
    "e2e: 端到端测试",
    "slow: 慢速测试",
]
```

---

## 5. Mock 策略

### 5.1 Mock LLM

```python
# tests/conftest.py
@pytest.fixture
def mock_llm_service():
    """Mock LLMService，struct结构化调用返回固定结果"""
    service = AsyncMock(spec=LLMService)
    
    service.structured_invoke.return_value = JdStructured(
        company="测试公司",
        position="Java 开发",
        salary_min=20,
        salary_max=30,
        city="北京",
        skills=["Java", "Spring"],
    )
    return service
```

### 5.2 Mock Playwright

```python
@pytest.fixture
def mock_playwright():
    """Mock Playwright，避免真实浏览器"""
    with patch("playwright.async_api.async_playwright") as mock:
        browser = AsyncMock()
        page = AsyncMock()
        page.inner_text.return_value = "测试 JD 内容"
        browser.new_page.return_value = page
        mock.return_value.__aenter__.return_value.chromium.launch.return_value = browser
        yield mock
```

### 5.3 Mock 数据库

```python
@pytest.fixture
async def async_session():
    """真实数据库 session（Testcontainers PostgreSQL）"""
    from testcontainers.postgres import PostgresContainer
    
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        engine = create_async_engine(pg.get_connection_url())
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        async with async_sessionmaker(engine)() as session:
            yield session
```

### 5.4 Celery Eager 模式

```python
# tests/conftest.py
@pytest.fixture(autouse=True)
def celery_eager_mode():
    """Celery 任务同步执行，方便测试"""
    celery_app.conf.task_always_eager = True
    yield
    celery_app.conf.task_always_eager = False
```

---

## 6. 测试数据库

### 6.1 Testcontainers

```python
# tests/conftest.py
@pytest.fixture(scope="session")
def postgres_container():
    from testcontainers.postgres import PostgresContainer
    container = PostgresContainer("pgvector/pgvector:pg16")
    container.start()
    yield container
    container.stop()
```

### 6.2 Alembic

测试库用 Alembic 初始化：

```python
@pytest.fixture(scope="session")
async def migrated_db(postgres_container):
    """运行所有 migration"""
    engine = create_async_engine(postgres_container.get_connection_url())
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
```

---

## 7. 关键测试场景

### 7.1 召回引擎

```python
# tests/integration/test_retrieval.py
@pytest.mark.asyncio
async def test_hybrid_search_better_than_single(async_session):
    """混合召回应优于单一策略"""
    # 准备 100 份简历
    resumes = await create_test_resumes(async_session, count=100)
    
    jd_text = "需要 Java 和 Kafka 经验，熟悉高并发"
    
    # 跑三种策略
    vector_results = await retrieval_service.vector_search(jd_text, 10)
    keyword_results = await retrieval_service.keyword_search(jd_text, 10)
    hybrid_results = await retrieval_service.hybrid_search(jd_text, 10)
    
    # 至少确保混合召回能返回结果
    assert len(hybrid_results) > 0
```

### 7.2 评估指标

```python
# tests/unit/test_evaluation.py
def test_recall_at_k():
    metrics = EvaluationService()
    results = [1, 2, 3, 4, 5]
    ground_truth = {2, 4}
    assert metrics.recall_at_k(results, ground_truth, 5) == 1.0  # 都召回了
    
    assert metrics.recall_at_k([1, 2, 3], {2, 4}, 3) == 0.5  # 只召回一半

def test_precision_at_k():
    metrics = EvaluationService()
    results = [1, 2, 3]
    ground_truth = {2, 4}
    assert metrics.precision_at_k(results, ground_truth, 3) == 1/3

def test_ndcg_at_k():
    metrics = EvaluationService()
    results = [ResumeScore(1, 0.9), ResumeScore(2, 0.8)]
    ground_truth = {1}
    score = metrics.ndcg_at_k(results, ground_truth, 2)
    assert 0 < score <= 1
```

### 7.3 定制化流程

```python
# tests/e2e/test_customization_flow.py
@pytest.mark.asyncio
async def test_full_customization_flow(client, sample_resume, sample_jd):
    # 1. 上传简历
    resume = await upload_resume(client, sample_resume)
    await wait_for_parse_complete(client, resume["id"])
    
    # 2. 提交 JD（粘贴）
    jd = await submit_jd_text(client, "Java 开发，要求 Kafka...")
    
    # 3. 发起定制化
    customization = await create_customization(client, jd["id"], resume["id"])
    
    # 4. 等待完成
    final = await wait_for_complete(client, customization["id"], timeout=120)
    
    # 5. 验证报告
    assert final["status"] == "COMPLETED"
    assert final["gap_report"]["match_score"] > 0
    assert len(final["customized_resume"]["experiences"]) > 0
    assert len(final["prediction"]["questions"]) == 5
    assert final["retrieval_metrics"]["hybrid"]["recall_at_10"] > 0
```

---

## 8. 性能测试（可选）

```python
# tests/performance/test_retrieval_perf.py
@pytest.mark.asyncio
@pytest.mark.slow
async def test_hybrid_search_p95_under_500ms(retrieval_service):
    """P95 延迟 < 500ms"""
    jd_text = "Java 开发，要求 Kafka、Redis、高并发"
    
    latencies = []
    for _ in range(100):
        start = time.time()
        await retrieval_service.hybrid_search(jd_text, 50)
        latencies.append((time.time() - start) * 1000)
    
    p95 = sorted(latencies)[94]
    assert p95 < 500, f"P95 延迟 {p95}ms 超过 500ms"
```

---

## 9. CI 集成

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    - run: pip install poetry
    - run: poetry install
    - run: poetry run pytest --cov=app --cov-report=xml --cov-fail-under=80
    - uses: codecov/codecov-action@v4
```

---

## 10. 面试讲点

1. **"测试覆盖率怎么保证？"**
   > pytest-cov + CI 卡线（核心模块 ≥ 85%，算法 ≥ 90%）。每次 PR 必须通过覆盖率检查。

2. **"LLM 调用怎么测？"**
   > Mock LLMService，业务逻辑用固定返回验证。Prompt 模板单独测渲染正确性。

3. **"集成测试用真库还是 mock？"**
   > 用 Testcontainers 起真实 PostgreSQL，避免 SQL 兼容性坑。Mock 数据库容易漏掉 SQL 错误。

4. **"Celery 任务怎么测？"**
   > `task_always_eager=True` 让任务同步执行，pytest 直接验证任务结果。