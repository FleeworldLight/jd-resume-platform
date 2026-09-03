# 异步任务设计

> Celery + Redis 实现简历解析、JD 抓取、定制化流水线。

---

## 1. 任务清单

| 任务 | 触发时机 | 预计耗时 | 重试 |
|---|---|---|---|
| `parse_resume_task` | 用户上传简历 | 5-10s | 2 次 |
| `index_resume_task` | 简历解析完成 | 3-5s | 2 次 |
| `crawl_jd_task` | 用户提交 JD URL | 30-60s | 2 次 |
| `structure_jd_task` | JD 抓取完成 | 3-5s | 2 次 |
| `customize_resume_task` | 用户发起定制化 | 30-60s | 2 次 |

---

## 2. Celery 配置

```python
# app/tasks/celery_app.py
from celery import Celery

celery_app = Celery(
    "jd_platform",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_track_started=True,
    task_time_limit=300,        # 硬超时 5 分钟
    task_soft_time_limit=240,   # 软超时 4 分钟
    worker_max_tasks_per_child=100,
    worker_prefetch_multiplier=1,
)
```

---

## 3. 任务实现

### 3.1 简历解析

```python
# app/tasks/resume_tasks.py
from app.services.resume_service import ResumeService
from app.tasks.celery_app import celery_app

@celery_app.task(bind=True, max_retries=2, name="parse_resume")
def parse_resume_task(self, resume_id: int):
    async def _run():
        async with async_session() as db:
            service = ResumeService(db)
            try:
                await service.parse_and_update(resume_id)
            except Exception as e:
                if self.request.retries < self.max_retries:
                    raise self.retry(exc=e, countdown=2 ** self.request.retries)
                else:
                    await service.mark_failed(resume_id, str(e))
                    raise
    
    asyncio.run(_run())
```

### 3.2 简历索引（向量化 + 全文检索）

```python
@celery_app.task(bind=True, max_retries=2, name="index_resume")
def index_resume_task(self, resume_id: int):
    async def _run():
        async with async_session() as db:
            service = RetrievalService(db)
            try:
                resume = await get_resume(db, resume_id)
                if not resume or not resume.resume_text:
                    return
                await service.index_resume(resume_id, resume.resume_text)
            except Exception as e:
                if self.request.retries < self.max_retries:
                    raise self.retry(exc=e, countdown=2 ** self.request.retries)
                else:
                    log.error("简历索引失败", resume_id=resume_id, error=str(e))
    
    asyncio.run(_run())
```

### 3.3 JD 抓取

```python
@celery_app.task(bind=True, max_retries=2, name="crawl_jd")
def crawl_jd_task(self, jd_id: int, url: str):
    async def _run():
        async with async_session() as db:
            service = JdService(db)
            try:
                await service.crawl_and_update(jd_id, url)
                # 抓取完成后自动触发结构化
                structure_jd_task.delay(jd_id)
            except Exception as e:
                if self.request.retries < self.max_retries:
                    raise self.retry(exc=e, countdown=2 ** self.request.retries)
                else:
                    await service.mark_failed(jd_id, str(e))
    
    asyncio.run(_run())
```

### 3.4 定制化主任务（DAG）

```python
@celery_app.task(bind=True, max_retries=2, name="customize_resume")
def customize_resume_task(self, customization_id: int):
    async def _run():
        async with async_session() as db:
            customization = await get_customization(db, customization_id)
            
            try:
                # 状态：PROCESSING
                await mark_processing(db, customization_id)
                
                # Step 1: 召回
                retrieval = await retrieval_service.hybrid_search(
                    query=customization.jd.raw_text,
                    top_k=50,
                )
                
                # Step 2: 差距分析
                gap = await gap_analysis_service.analyze(
                    jd=customization.jd,
                    resume=customization.base_resume,
                )
                
                # Step 3: 定制简历
                customized = await customize_service.customize(
                    jd=customization.jd,
                    resume=customization.base_resume,
                    gap=gap,
                )
                
                # Step 4: 押题
                prediction = await predict_service.predict(
                    jd=customization.jd,
                    customized_resume=customized,
                )
                
                # Step 5: 落库
                await mark_completed(
                    db,
                    customization_id,
                    gap_report=gap,
                    customized_resume=customized,
                    prediction=prediction,
                    retrieval_metrics=retrieval.metrics,
                )
            
            except Exception as e:
                if self.request.retries < self.max_retries:
                    await db.rollback()
                    raise self.retry(exc=e, countdown=2 ** self.request.retries)
                else:
                    await mark_failed(db, customization_id, str(e))
    
    asyncio.run(_run())
```

---

## 4. 任务编排

### 4.1 上传简历后的链式调用

```python
# app/services/resume_service.py
async def upload_and_save(self, file: UploadFile) -> Resume:
    # 1. 保存文件 + 入库
    resume = await self._save_resume(file)
    
    # 2. 触发解析任务
    parse_resume_task.delay(resume.id)
    
    return resume

# app/tasks/resume_tasks.py
@celery_app.task(bind=True, name="parse_resume")
def parse_resume_task(self, resume_id: int):
    async def _run():
        # ... 解析逻辑
        await mark_parsed(resume_id)
    
    asyncio.run(_run())
    
    # 解析完成后触发索引
    index_resume_task.delay(resume_id)
```

### 4.2 JD URL 抓取后的链式调用

```python
@celery_app.task(bind=True, name="crawl_jd")
def crawl_jd_task(self, jd_id: int, url: str):
    async def _run():
        # ... 抓取逻辑
        await mark_crawled(jd_id, raw_text)
    
    asyncio.run(_run())
    
    # 抓取后触发结构化
    structure_jd_task.delay(jd_id)
```

---

## 5. 幂等性

**关键问题**：同一任务被重复消费，不能重复扣费、不能重复入库。

### 5.1 简历解析幂等

```python
async def parse_and_update(self, resume_id: int):
    resume = await get_resume(db, resume_id)
    if resume.parse_status == "COMPLETED":
        return  # 已完成，跳过
    # ... 解析逻辑
```

### 5.2 定制化幂等

```python
async def mark_processing(self, db, customization_id):
    # 用乐观锁防止重复处理
    result = await db.execute(
        update(Customization)
        .where(Customization.id == customization_id)
        .where(Customization.status == "PENDING")
        .values(status="PROCESSING", started_at=datetime.utcnow())
    )
    if result.rowcount == 0:
        raise BusinessException(ErrorCode.CUSTOMIZATION_ALREADY_PROCESSING)
```

---

## 6. 状态机

```
PENDING → PROCESSING → COMPLETED
                    ↘ FAILED → (manual retry) → PENDING
```

```python
class AsyncTaskStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
```

---

## 7. 监控

### 7.1 Celery Flower

```bash
celery -A app.tasks.celery_app flower --port=5555
```

访问 `http://localhost:5555` 看任务状态、worker 健康、队列长度。

### 7.2 日志埋点

```python
@celery_app.task(bind=True, name="customize_resume")
def customize_resume_task(self, customization_id: int):
    log.info("task_started", task="customize", customization_id=customization_id)
    start = time.time()
    try:
        # ...
        log.info("task_completed", task="customize", 
                 customization_id=customization_id,
                 duration_ms=int((time.time() - start) * 1000))
    except Exception as e:
        log.error("task_failed", task="customize",
                  customization_id=customization_id,
                  error=str(e))
        raise
```

---

## 8. 本地开发

```bash
# 启动 worker
celery -A app.tasks.celery_app worker -l info

# 启动 beat（定时任务，可选）
celery -A app.tasks.celery_app beat -l info

# 启动 Flower（监控）
celery -A app.tasks.celery_app flower

# 测试模式（同步执行，不走 Redis）
CELERY_TASK_ALWAYS_EAGER=true pytest
```

---

## 9. 面试讲点

1. **"为什么用 Celery + Redis 不用 Kafka？"**
   > 简化部署（Redis 已经在了），任务量不大（个人项目）。Celery broker 抽象了，换 Kafka 改配置即可。

2. **"任务失败怎么办？"**
   > Celery 自带重试 + 指数退避（1s/2s/4s）。重试耗尽后标记 FAILED，前端展示错误并允许手动重试。

3. **"怎么保证任务不重复消费？"**
   > 状态机 + 乐观锁。处理前先把状态从 PENDING 改成 PROCESSING，rowcount=0 说明已被其他 worker 抢走，直接返回。

4. **"Celery 异步任务怎么测试？"**
   > `CELERY_TASK_ALWAYS_EAGER=true` 让任务同步执行，pytest 直接调用 task 函数。