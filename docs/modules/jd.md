# JD 模块

> JD 粘贴、抓取、结构化抽取。

---

## 1. 支持的来源

| 来源 | 是否支持 | 爬虫策略 |
|---|---|---|
| 手动粘贴 | ✅ 永远支持 | - |
| 牛客（nowcoder） | ✅ | Playwright |
| Boss 直聘（zhipin/boss） | ✅ | Playwright |
| 其他 | ❌ 拒绝 | 提示粘贴 |

---

## 2. 数据模型

```python
# app/db/models/jd.py
class Jd(Base):
    __tablename__ = "jds"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))  # NOWCODER / BOSS / MANUAL
    source_url: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str] = mapped_column(Text)
    
    # 结构化字段
    company: Mapped[str | None] = mapped_column(String(128))
    position: Mapped[str | None] = mapped_column(String(128))
    salary_min: Mapped[int | None] = mapped_column()
    salary_max: Mapped[int | None] = mapped_column()
    city: Mapped[str | None] = mapped_column(String(128))
    experience: Mapped[str | None] = mapped_column(String(64))
    education: Mapped[str | None] = mapped_column(String(64))
    skills: Mapped[list | None] = mapped_column(JSONB)
    responsibilities: Mapped[list | None] = mapped_column(JSONB)
    requirements: Mapped[list | None] = mapped_column(JSONB)
    structured: Mapped[dict | None] = mapped_column(JSONB)
    
    crawl_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    crawl_error: Mapped[str | None] = mapped_column(Text)
    
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
```

---

## 3. 接口

```python
# app/api/jds.py
router = APIRouter(prefix="/api/jds", tags=["jds"])

@router.post("/text", response_model=Result[JdResponse])
@limiter.limit("10/minute")
async def submit_jd_text(request: Request, req: JdTextRequest, service: JdService = Depends()):
    """粘贴 JD 文本（同步结构化）"""
    jd = await service.create_from_text(req.text)
    return Result.ok(JdResponse.from_entity(jd))

@router.post("/url", response_model=Result[JdResponse])
@limiter.limit("2/second")
async def submit_jd_url(request: Request, req: JdUrlRequest, service: JdService = Depends()):
    """提交牛客/Boss URL（异步抓取 + 结构化）"""
    jd = await service.create_from_url(req.url)
    return Result.ok(JdResponse.from_entity(jd))

@router.get("", response_model=Result[JdListResponse])
async def list_jds(page: int = 1, page_size: int = 20, service: JdService = Depends()):
    jds, total = await service.list(page, page_size)
    return Result.ok(JdList(items=jds, total=total))

@router.get("/{jd_id}", response_model=Result[JdResponse])
async def get_jd(jd_id: int, service: JdService = Depends()):
    jd = await service.get(jd_id)
    return Result.ok(JdResponse.from_entity(jd))

@router.delete("/{jd_id}", response_model=Result[None])
async def delete_jd(jd_id: int, service: JdService = Depends()):
    await service.delete(jd_id)
    return Result.ok(message="删除成功")

@router.get("/{jd_id}/status", response_model=Result[JdStatusResponse])
async def get_jd_status(jd_id: int, service: JdService = Depends()):
    status = await service.get_status(jd_id)
    return Result.ok(status)
```

---

## 4. Service 实现

```python
# app/services/jd_service.py
class JdService:
    SUPPORTED_DOMAINS = {
        "nowcoder": "NOWCODER",
        "zhipin": "BOSS",
        "boss": "BOSS",
        "boos": "BOSS",  # 拼写错误兼容
    }
    
    def __init__(self, db: AsyncSession, llm_service: LLMService):
        self.db = db
        self.llm_service = llm_service
    
    def _detect_source(self, url: str) -> str:
        for domain, source in self.SUPPORTED_DOMAINS.items():
            if domain in url:
                return source
        raise BusinessException(
            ErrorCode.JD_SOURCE_UNSUPPORTED,
            "暂不支持该 JD 来源，请粘贴 JD 文本"
        )
    
    async def create_from_text(self, text: str) -> Jd:
        # 1. 创建记录
        jd = Jd(source="MANUAL", raw_text=text, crawl_status="COMPLETED")
        self.db.add(jd)
        await self.db.flush()
        
        # 2. 同步结构化抽取
        try:
            structured = await self.llm_service.structured_invoke(
                prompt_template=JD_EXTRACT_PROMPT,
                input_vars={"jd_text": text},
                output_schema=JdStructured,
            )
            self._apply_structured(jd, structured)
            await self.db.commit()
        except Exception as e:
            jd.crawl_error = str(e)[:500]
            await self.db.commit()
            raise
        
        return jd
    
    async def create_from_url(self, url: str) -> Jd:
        # 1. 校验来源
        source = self._detect_source(url)
        
        # 2. 创建记录
        jd = Jd(source=source, source_url=url, raw_text="", crawl_status="PENDING")
        self.db.add(jd)
        await self.db.commit()
        
        # 3. 触发异步抓取
        crawl_jd_task.delay(jd.id, url)
        
        return jd
    
    async def crawl_and_update(self, jd_id: int, url: str):
        jd = await self.get(jd_id)
        if not jd:
            raise BusinessException(ErrorCode.JD_NOT_FOUND)
        
        if jd.crawl_status == "COMPLETED":
            return  # 已完成，跳过
        
        jd.crawl_status = "PROCESSING"
        await self.db.commit()
        
        try:
            # 选择爬虫策略
            strategy = self._get_crawler_strategy(jd.source)
            
            # 抓取
            raw_text = await strategy.crawl(url)
            
            if not raw_text or len(raw_text) < 50:
                raise BusinessException(ErrorCode.JD_CRAWL_FAILED, "抓取内容为空或过短")
            
            # 更新原文
            jd.raw_text = raw_text
            jd.crawl_status = "PARSED"  # 抓取完成，等结构化
            await self.db.commit()
            
            # 触发结构化
            structure_jd_task.delay(jd_id)
        except Exception as e:
            jd.crawl_status = "FAILED"
            jd.crawl_error = str(e)[:500]
            await self.db.commit()
            raise
    
    async def structure_jd(self, jd_id: int):
        jd = await self.get(jd_id)
        if not jd or not jd.raw_text:
            return
        
        try:
            structured = await self.llm_service.structured_invoke(
                prompt_template=JD_EXTRACT_PROMPT,
                input_vars={"jd_text": jd.raw_text},
                output_schema=JdStructured,
            )
            self._apply_structured(jd, structured)
            jd.crawl_status = "COMPLETED"
            await self.db.commit()
        except Exception as e:
            jd.crawl_error = str(e)[:500]
            await self.db.commit()
            raise
    
    def _apply_structured(self, jd: Jd, s: JdStructured):
        jd.company = s.company
        jd.position = s.position
        jd.salary_min = s.salary_min
        jd.salary_max = s.salary_max
        jd.city = s.city
        jd.experience = s.experience
        jd.education = s.education
        jd.skills = s.skills
        jd.responsibilities = s.responsibilities
        jd.requirements = s.requirements
        jd.structured = s.model_dump()
```

---

## 5. 爬虫策略

### 5.1 接口

```python
# app/crawler/strategies/base.py
from typing import Protocol

class JdCrawler(Protocol):
    async def crawl(self, url: str) -> str:
        """抓取 JD，返回原始文本"""
        ...
```

### 5.2 牛客爬虫

```python
# app/crawler/strategies/nowcoder.py
import random
from pathlib import Path
import yaml
from playwright.async_api import async_playwright

UA_POOL = yaml.safe_load(Path("app/crawler/user_agents.yml").read_text())

class NowcoderCrawler:
    async def crawl(self, url: str) -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            ctx = await browser.new_context(
                user_agent=random.choice(UA_POOL),
                viewport={"width": 1920, "height": 1080},
            )
            page = await ctx.new_page()
            
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)
                # 牛客 JD 详情页正文 class
                text = await page.inner_text("body")
                return text
            finally:
                await browser.close()
```

### 5.3 Boss 爬虫

```python
# app/crawler/strategies/boss.py
class BossCrawler:
    async def crawl(self, url: str) -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            ctx = await browser.new_context(
                user_agent=random.choice(UA_POOL),
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
            )
            page = await ctx.new_page()
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Boss 经常要验证码，先等几秒
                await page.wait_for_timeout(3000)
                
                # 尝试不同选择器
                for selector in [".job-detail", ".job-sec-text", "body"]:
                    try:
                        await page.wait_for_selector(selector, timeout=5000)
                        text = await page.inner_text(selector)
                        if text and len(text) > 100:
                            return text
                    except:
                        continue
                
                return await page.inner_text("body")
            finally:
                await browser.close()
```

### 5.4 工厂

```python
# app/crawler/factory.py
def get_crawler(source: str) -> JdCrawler:
    if source == "NOWCODER":
        return NowcoderCrawler()
    elif source == "BOSS":
        return BossCrawler()
    else:
        raise BusinessException(ErrorCode.JD_SOURCE_UNSUPPORTED)
```

---

## 6. 状态机

```
PENDING → PROCESSING → PARSED → COMPLETED
                          ↓        ↓
                          FAILED   FAILED
```

- **PENDING**：刚提交，未开始
- **PROCESSING**：正在抓取
- **PARSED**：抓取完成，等待结构化抽取
- **COMPLETED**：结构化完成
- **FAILED**：任意阶段失败

---

## 7. 测试用例

```python
# tests/unit/services/test_jd_service.py
@pytest.mark.asyncio
async def test_detect_source_nowcoder():
    service = JdService(db, llm)
    assert service._detect_source("https://www.nowcoder.com/jobs/123") == "NOWCODER"

@pytest.mark.asyncio
async def test_detect_source_unsupported():
    service = JdService(db, llm)
    with pytest.raises(BusinessException) as exc:
        service._detect_source("https://example.com/jobs/123")
    assert exc.value.code == 2004

@pytest.mark.asyncio
async def test_create_from_text_success(jd_service, sample_jd_text):
    jd = await jd_service.create_from_text(sample_jd_text)
    assert jd.source == "MANUAL"
    assert jd.crawl_status == "COMPLETED"
    assert jd.company is not None

# tests/integration/api/test_jd_api.py
@pytest.mark.asyncio
async def test_submit_jd_url_unsupported(client):
    response = await client.post("/api/jds/url", json={"url": "https://lagou.com/jobs/123"})
    assert response.json()["code"] == 2004
```

---

## 8. 面试讲点

1. **"为什么只支持牛客和 Boss？"**
   > 简化爬虫实现，明确责任边界。其他网站反爬严、合规风险高，提示用户手动粘贴更安全。

2. **"JD 结构化抽取为什么用 LLM 而不是正则？"**
   > JD 格式千变万化（牛客/Boss 字段差异、用户粘贴格式不一），正则维护成本高。LLM 抽取更鲁棒，Few-shot 可以覆盖大多数格式。

3. **"爬虫失败怎么兜底？"**
   > 抓取失败时错误信息写库，前端展示错误。用户可以手动粘贴 JD 文本，永远支持。

4. **"反爬措施有哪些？"**
   > UA 池轮换、随机延迟、headless 浏览器、失败重试、不持久化登录态。单 IP 限流 2 QPS。