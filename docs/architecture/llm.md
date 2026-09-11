# LLM 调用规范

> **文档状态：部分过时（2026-09-11 标注）**
>
> 本文写于项目采用 Docker + PostgreSQL + pgvector + Redis + Celery 架构的阶段。
> 当前实际架构已简化为 SQLite + mock LLM provider + 无 Celery 的同步执行，详见根目录 README.md。
> 下文涉及 Docker / Postgres / pgvector / Redis / Celery / weasyprint 的段落仅作历史设计参考，不代表现状。

> 统一 LLM 调用入口：结构化输出 + 多 Provider + 重试 + 降级。

---

## 1. 设计原则

- **唯一入口**：所有 LLM 调用走 `LLMService`，禁止在业务代码裸调
- **结构化输出优先**：用 Pydantic schema + `with_structured_output`
- **失败可重试**：用 `tenacity`，指数退避
- **降级兜底**：关键路径（简历定制）失败时返回默认响应，不让用户卡住

---

## 2. 多 Provider 抽象

### 2.1 Provider 配置

```python
# app/db/models/llm_provider.py
class LLMProvider(Base):
    __tablename__ = "llm_providers"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    provider_type: Mapped[str] = mapped_column(String(32))  # OPENAI_COMPATIBLE / DASHSCOPE
    base_url: Mapped[str | None] = mapped_column(String(512))
    api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    chat_model: Mapped[str | None] = mapped_column(String(128))
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    is_default: Mapped[bool] = mapped_column(default=False)
    enabled: Mapped[bool] = mapped_column(default=True)
```

### 2.2 默认 Provider 解析

```python
class LLMService:
    async def _get_provider(self, name: str | None) -> LLMProvider:
        if name:
            provider = await self._get_provider_by_name(name)
        else:
            provider = await self._get_default_provider()
        
        if not provider or not provider.enabled:
            raise BusinessException(ErrorCode.LLM_PROVIDER_DISABLED)
        return provider
```

### 2.3 ChatModel 实例化

```python
def _create_chat_model(self, provider: LLMProvider) -> BaseChatModel:
    api_key = decrypt_api_key(provider.api_key_encrypted)
    
    if provider.provider_type == "DASHSCOPE":
        from langchain_community.chat_models.tongyi import ChatTongyi
        return ChatTongyi(
            model=provider.chat_model,
            dashscope_api_key=api_key,
        )
    elif provider.provider_type == "OPENAI_COMPATIBLE":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url=provider.base_url,
            api_key=api_key,
            model=provider.chat_model,
        )
    else:
        raise BusinessException(ErrorCode.LLM_PROVIDER_TYPE_UNKNOWN)
```

---

## 3. 结构化输出

### 3.1 Prompt 模板外置

所有 Prompt 在 `app/prompts/*.py`：

```python
# app/prompts/jd_extract.py
from langchain_core.prompts import ChatPromptTemplate

JD_EXTRACT_SYSTEM = """你是一个招聘信息解析专家，从给定文本中提取结构化信息。
输出严格的 JSON 格式，包含字段：company, position, salary_min, salary_max, city,
experience, education, skills, responsibilities, requirements。
- skills: 数组，提取所有技术关键词
- responsibilities: 数组，工作职责
- requirements: 数组，岗位要求"""

JD_EXTRACT_USER = """请解析以下 JD 文本：

{jd_text}

请输出 JSON。"""

JD_EXTRACT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", JD_EXTRACT_SYSTEM),
    ("user", JD_EXTRACT_USER),
])
```

### 3.2 Pydantic Schema

```python
# app/schemas/jd.py
from pydantic import BaseModel, Field

class JdStructured(BaseModel):
    company: str | None = Field(default=None, description="公司名")
    position: str | None = Field(default=None, description="岗位名称")
    salary_min: int | None = Field(default=None, description="最低薪资 K")
    salary_max: int | None = Field(default=None, description="最高薪资 K")
    city: str | None = Field(default=None, description="工作城市")
    experience: str | None = Field(default=None, description="经验要求")
    education: str | None = Field(default=None, description="学历要求")
    skills: list[str] = Field(default_factory=list, description="技能关键词")
    responsibilities: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
```

### 3.3 结构化调用

```python
from langchain_core.prompts import ChatPromptTemplate
from tenacity import retry, stop_after_attempt, wait_exponential

class LLMService:
    async def structured_invoke[T](
        self,
        prompt_template: ChatPromptTemplate,
        input_vars: dict,
        output_schema: type[T],
        provider_name: str | None = None,
        max_retries: int = 3,
    ) -> T:
        provider = await self._get_provider(provider_name)
        chat_model = self._create_chat_model(provider)
        structured_llm = chat_model.with_structured_output(
            output_schema,
            method="function_calling",  # 或 json_mode
        )
        
        chain = prompt_template | structured_llm
        
        return await self._invoke_with_retry(
            chain, input_vars, max_retries
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    async def _invoke_with_retry(self, chain, input_vars, max_retries):
        return await chain.ainvoke(input_vars)
```

---

## 4. 各业务调用点

### 4.1 JD 结构化抽取

```python
# app/services/jd_service.py
class JdService:
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
    
    async def extract_structure(self, raw_text: str) -> JdStructured:
        return await self.llm_service.structured_invoke(
            prompt_template=JD_EXTRACT_PROMPT,
            input_vars={"jd_text": raw_text},
            output_schema=JdStructured,
        )
```

### 4.2 差距分析

```python
# app/services/gap_analysis_service.py
GAP_ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个求职顾问，根据 JD 和用户简历，输出差距分析。
match_score: 0-100 的匹配度评分
matched_skills: 已匹配的技能
missing_skills: 缺失的技能 + 优先级 + 原因
experience_gaps: 经验差距
recommended_focus: 简历定制重点"""),
    ("user", """JD:
{jd_text}

JD 结构化:
{jd_structured}

用户简历:
{resume_text}

请输出 JSON。""")
])

async def analyze(self, jd: JdEntity, resume: ResumeEntity) -> GapReport:
    return await self.llm_service.structured_invoke(
        prompt_template=GAP_ANALYSIS_PROMPT,
        input_vars={
            "jd_text": jd.raw_text,
            "jd_structured": json.dumps(jd.structured),
            "resume_text": resume.resume_text,
        },
        output_schema=GapReport,
    )
```

### 4.3 定制简历生成

```python
# app/services/customize_service.py
async def customize(
    self,
    jd: JdEntity,
    resume: ResumeEntity,
    gap: GapReport,
) -> CustomizedResume:
    return await self.llm_service.structured_invoke(
        prompt_template=CUSTOMIZE_PROMPT,
        input_vars={
            "jd_text": jd.raw_text,
            "resume_text": resume.resume_text,
            "gap_report": gap.model_dump_json(),
        },
        output_schema=CustomizedResume,
    )
```

### 4.4 押题生成

```python
# app/services/predict_service.py
async def predict(
    self,
    jd: JdEntity,
    customized_resume: CustomizedResume,
    question_count: int = 5,
) -> InterviewPrediction:
    return await self.llm_service.structured_invoke(
        prompt_template=PREDICT_PROMPT,
        input_vars={
            "jd_text": jd.raw_text,
            "customized_resume": customized_resume.model_dump_json(),
            "question_count": question_count,
        },
        output_schema=InterviewPrediction,
    )
```

---

## 5. 流式输出（可选）

某些场景需要流式（SSE）：

```python
from fastapi.responses import StreamingResponse

@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """流式对话（前端打字机效果）"""
    
    async def generate():
        chat_model = await llm_service.get_chat_model()
        async for chunk in chat_model.astream(req.messages):
            yield chunk.content
    
    return StreamingResponse(generate(), media_type="text/event-stream")
```

**本项目流式用的场景**：
- 知识库问答（如果做）
- 简历定制实时预览（可选增强）

---

## 6. 错误处理

### 6.1 错误码

```python
class ErrorCode:
    LLM_PROVIDER_DISABLED = ("LLM_001", "模型未启用")
    LLM_PROVIDER_TYPE_UNKNOWN = ("LLM_002", "未知 Provider 类型")
    LLM_API_KEY_INVALID = ("LLM_003", "API Key 无效")
    LLM_RATE_LIMITED = ("LLM_004", "模型调用限流")
    LLM_TIMEOUT = ("LLM_005", "模型调用超时")
    LLM_OUTPUT_INVALID = ("LLM_006", "模型输出格式错误")
```

### 6.2 重试策略

| 错误类型 | 是否重试 | 退避策略 |
|---|---|---|
| 网络错误 | ✅ | 指数退避 1/2/4s |
| 限流（429） | ✅ | 指数退避 |
| 超时 | ✅ | 指数退避 |
| 输出格式错误 | ✅ | 重试（让模型再生成）|
| API Key 无效 | ❌ | 直接抛错 |
| 模型不存在 | ❌ | 直接抛错 |

### 6.3 降级兜底

定制化主任务失败时：

```python
@celery_app.task(bind=True, max_retries=2)
def customize_resume_task(self, customization_id: int):
    try:
        result = run_customization(customization_id)
    except Exception as e:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=2 ** self.request.retries)
        else:
            # 重试耗尽，标记 FAILED，让用户看到错误
            mark_failed(customization_id, str(e))
```

---

## 7. 限流

LLM 接口限流（5 QPS per IP）：

```python
# app/core/rate_limit.py
from slowapi import Limiter

limiter = Limiter(key_func=get_remote_address)

@router.post("/customizations")
@limiter.limit("5/second")
async def create_customization(req: CustomizationRequest):
    ...
```

---

## 8. 测试

### 8.1 Mock LLM

```python
# tests/conftest.py
@pytest.fixture
def mock_llm_service():
    """Mock LLM Service，返回固定结果"""
    service = AsyncMock(spec=LLMService)
    
    service.structured_invoke.return_value = JdStructured(
        company="测试公司",
        position="测试岗位",
        skills=["Java", "Spring"]
    )
    return service
```

### 8.2 Prompt 渲染测试

```python
# tests/unit/prompts/test_jd_extract_prompt.py
def test_jd_extract_prompt_renders():
    prompt = JD_EXTRACT_PROMPT.format_messages(jd_text="测试JD")
    assert len(prompt) == 2
    assert "测试JD" in prompt[1].content
```

---

## 9. 面试讲点

1. **"为什么用 LangChain 而不是直接调 OpenAI SDK？"**
   > LangChain 提供多 Provider 抽象、结构化输出、Prompt 模板管理，统一接口后续切模型零成本。

2. **"结构化输出怎么保证稳定性？"**
   > Pydantic schema + `with_structured_output` + 重试机制。模型返回 JSON 解析失败时重试，让模型重新生成。

3. **"为什么不直接用 OpenAI Function Calling？"**
   > Function Calling 是 OpenAI 专属能力，其他模型（DashScope/Kimi）不支持。LangChain `with_structured_output` 抽象了下层，可自动降级到 JSON Mode 或 prompt 工程。

4. **"Prompt 怎么管理？"**
   > 全部外置到 `app/prompts/*.py`，每个文件导出一个 `ChatPromptTemplate`。不允许在 Service 代码里拼接 Prompt，方便版本管理和 A/B 测试。