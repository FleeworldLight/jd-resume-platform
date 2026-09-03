# 定制化模块

> 差距分析 + 定制简历 + 押题生成 + 评估指标。

---

## 1. 端到端流程

```
[用户发起定制化]
  POST /api/customizations { jd_id, resume_id }
  ↓
[定制化记录入库, status=PENDING]
  ↓
[Celery: customize_resume_task]
  ├─ Step 1: 召回（pgvector + PG tsvector 混合打分）
  ├─ Step 2: 差距分析（LLM）
  ├─ Step 3: 定制简历生成（LLM）
  ├─ Step 4: 押题生成（LLM）
  ├─ Step 5: 评估指标计算
  └─ Step 6: 落库, status=COMPLETED
  ↓
[前端轮询]
  GET /api/customizations/{id}/status
  ↓ COMPLETED
[展示报告 + 可导出 PDF]
```

---

## 2. 数据模型

```python
# app/db/models/customization.py
class Customization(Base):
    __tablename__ = "customizations"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    jd_id: Mapped[int] = mapped_column(ForeignKey("jds.id"))
    base_resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id"))
    
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(default=0)
    
    gap_report: Mapped[dict | None] = mapped_column(JSONB)
    customized_resume: Mapped[dict | None] = mapped_column(JSONB)
    prediction: Mapped[dict | None] = mapped_column(JSONB)
    retrieval_metrics: Mapped[dict | None] = mapped_column(JSONB)
    matched_resumes: Mapped[list | None] = mapped_column(JSONB)
    
    provider_used: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()
    
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
```

---

## 3. 接口

```python
# app/api/customizations.py
router = APIRouter(prefix="/api/customizations", tags=["customizations"])

@router.post("", response_model=Result[CustomizationResponse])
@limiter.limit("5/minute")
async def create_customization(
    request: Request,
    req: CustomizationCreateRequest,
    service: CustomizationService = Depends(),
):
    """发起定制化任务"""
    customization = await service.create(req.jd_id, req.base_resume_id)
    return Result.ok(CustomizationResponse.from_entity(customization))

@router.get("", response_model=Result[CustomizationListResponse])
async def list_customizations(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    service: CustomizationService = Depends(),
):
    customizations, total = await service.list(page, page_size, status)
    return Result.ok(CustomizationList(items=customizations, total=total))

@router.get("/{customization_id}", response_model=Result[CustomizationDetailResponse])
async def get_customization(customization_id: int, service: CustomizationService = Depends()):
    c = await service.get_with_details(customization_id)
    return Result.ok(c)

@router.get("/{customization_id}/status", response_model=Result[CustomizationStatusResponse])
async def get_customization_status(customization_id: int, service: CustomizationService = Depends()):
    """轮询用：轻量响应"""
    return Result.ok(await service.get_status(customization_id))

@router.delete("/{customization_id}", response_model=Result[None])
async def delete_customization(customization_id: int, service: CustomizationService = Depends()):
    await service.delete(customization_id)
    return Result.ok(message="删除成功")

@router.post("/{customization_id}/retry", response_model=Result[None])
async def retry_customization(customization_id: int, service: CustomizationService = Depends()):
    await service.retry(customization_id)
    return Result.ok(message="重试任务已提交")

@router.get("/{customization_id}/pdf")
async def export_pdf(customization_id: int, service: CustomizationService = Depends()):
    pdf_bytes = await service.export_pdf(customization_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=customization_{customization_id}.pdf"},
    )
```

---

## 4. Schema 定义

```python
# app/schemas/customization.py
from pydantic import BaseModel, Field

class GapReport(BaseModel):
    match_score: int = Field(..., ge=0, le=100)
    matched_skills: list[str]
    missing_skills: list[MissingSkill]
    experience_gaps: list[ExperienceGap]
    recommended_focus: list[str]

class MissingSkill(BaseModel):
    skill: str
    priority: str = Field(..., pattern="^(HIGH|MEDIUM|LOW)$")
    reason: str

class ExperienceGap(BaseModel):
    aspect: str
    current: str
    expected: str

class CustomizedResume(BaseModel):
    summary: str = Field(..., description="针对 JD 重写的个人简介")
    skills: list[str] = Field(..., description="按 JD 命中度排序的技能")
    experiences: list[Experience] = Field(..., description="项目经历, 已优化")
    education: list[Education] = Field(..., description="教育经历")
    highlights: list[str] = Field(..., description="针对 JD 强调的亮点")

class Experience(BaseModel):
    title: str
    company: str
    duration: str
    description: str
    achievements: list[str]
    tech_stack: list[str]

class Education(BaseModel):
    school: str
    major: str
    degree: str
    duration: str

class InterviewPrediction(BaseModel):
    questions: list[PredictedQuestion]

class PredictedQuestion(BaseModel):
    category: str  # 技术深度 / 项目经验 / 软技能
    difficulty: str = Field(..., pattern="^(EASY|MEDIUM|HARD)$")
    question: str
    star_answer: StarAnswer
    key_points: list[str]
    hit_reason: str

class StarAnswer(BaseModel):
    situation: str
    task: str
    action: str
    result: str

class RetrievalMetrics(BaseModel):
    recall_at_10: float
    precision_at_10: float
    ndcg_at_10: float
    vector_only_metrics: dict
    keyword_only_metrics: dict
```

---

## 5. Service 实现

### 5.1 定制化主服务

```python
# app/services/customization_service.py
class CustomizationService:
    def __init__(
        self,
        db: AsyncSession,
        retrieval_service: RetrievalService,
        gap_analysis_service: GapAnalysisService,
        customize_service: CustomizeService,
        predict_service: PredictService,
        evaluation_service: EvaluationService,
    ):
        self.db = db
        self.retrieval_service = retrieval_service
        self.gap_analysis_service = gap_analysis_service
        self.customize_service = customize_service
        self.predict_service = predict_service
        self.evaluation_service = evaluation_service
    
    async def create(self, jd_id: int, resume_id: int) -> Customization:
        # 校验输入
        jd = await self._get_jd(jd_id)
        resume = await self._get_resume(resume_id)
        
        if jd.crawl_status != "COMPLETED":
            raise BusinessException(ErrorCode.CUSTOMIZATION_INVALID_INPUT,
                                    "JD 未完成结构化抽取")
        if resume.parse_status != "COMPLETED":
            raise BusinessException(ErrorCode.CUSTOMIZATION_INVALID_INPUT,
                                    "简历未完成解析")
        
        # 创建记录
        customization = Customization(
            jd_id=jd_id,
            base_resume_id=resume_id,
            status="PENDING",
        )
        self.db.add(customization)
        await self.db.commit()
        
        # 触发异步任务
        customize_resume_task.delay(customization.id)
        
        return customization
    
    async def execute(self, customization_id: int):
        """Celery 任务调用：执行定制化"""
        customization = await self._get_customization(customization_id)
        jd = await self._get_jd(customization.jd_id)
        resume = await self._get_resume(customization.base_resume_id)
        
        # Step 1: 召回 + 评估
        retrieval = await self.retrieval_service.hybrid_search(
            query=jd.raw_text,
            top_k=50,
        )
        
        # 评估基线策略
        vector_metrics = self.evaluation_service.evaluate(
            await self.retrieval_service.vector_search(jd.raw_text, 10),
            ground_truth={customization.base_resume_id},
        )
        keyword_metrics = self.evaluation_service.evaluate(
            await self.retrieval_service.keyword_search(jd.raw_text, 10),
            ground_truth={customization.base_resume_id},
        )
        hybrid_metrics = self.evaluation_service.evaluate(
            retrieval.results,
            ground_truth={customization.base_resume_id},
        )
        
        retrieval_metrics = {
            "hybrid": hybrid_metrics.dict(),
            "vector_only": vector_metrics.dict(),
            "keyword_only": keyword_metrics.dict(),
        }
        
        # Step 2: 差距分析
        gap = await self.gap_analysis_service.analyze(jd=jd, resume=resume)
        
        # Step 3: 定制简历
        customized = await self.customize_service.customize(
            jd=jd, resume=resume, gap=gap
        )
        
        # Step 4: 押题
        prediction = await self.predict_service.predict(
            jd=jd, customized_resume=customized, question_count=5
        )
        
        # Step 5: 落库
        customization.gap_report = gap.model_dump()
        customization.customized_resume = customized.model_dump()
        customization.prediction = prediction.model_dump()
        customization.retrieval_metrics = retrieval_metrics
        customization.matched_resumes = [r.dict() for r in retrieval.results[:10]]
        customization.status = "COMPLETED"
        customization.completed_at = datetime.utcnow()
        await self.db.commit()
```

### 5.2 差距分析

```python
# app/services/gap_analysis_service.py
GAP_ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位资深求职顾问。
请根据 JD 和用户简历，输出差距分析报告。

要求:
- match_score: 0-100 的整数，反映简历与 JD 的整体匹配度
- matched_skills: 用户已具备、JD 要求的技能
- missing_skills: 用户缺失的技能，每个包含 skill/priority(HIGH/MEDIUM/LOW)/reason
- experience_gaps: 经验差距，如高并发经验、行业经验等
- recommended_focus: 简历定制建议重点

输出严格的 JSON 格式。"""),
    ("user", """JD 文本:
{jd_text}

JD 结构化:
{jd_structured}

用户简历:
{resume_text}

请输出 JSON。"""),
])

class GapAnalysisService:
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
    
    async def analyze(self, jd: Jd, resume: Resume) -> GapReport:
        return await self.llm_service.structured_invoke(
            prompt_template=GAP_ANALYSIS_PROMPT,
            input_vars={
                "jd_text": jd.raw_text,
                "jd_structured": json.dumps(jd.structured, ensure_ascii=False),
                "resume_text": resume.resume_text,
            },
            output_schema=GapReport,
        )
```

### 5.3 定制简历

```python
# app/services/customize_service.py
CUSTOMIZE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位专业的简历优化专家。
请根据 JD 和差距报告，重新组织用户的简历，让其更贴合 JD。

要求:
- 不允许伪造经历、项目、技术栈
- 允许调整表述顺序、突出与 JD 相关的部分
- 个人简介要针对 JD 重写
- 技能顺序按 JD 命中度排序
- 项目经历要把与 JD 相关的放前面，相关性低的压缩
- 项目描述增加量化数据和与 JD 相关的关键词

输出严格的 JSON 格式。"""),
    ("user", """JD:
{jd_text}

原简历:
{resume_text}

差距报告:
{gap_report}

请输出定制版简历的 JSON。"""),
])

class CustomizeService:
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
    
    async def customize(self, jd: Jd, resume: Resume, gap: GapReport) -> CustomizedResume:
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

### 5.4 押题生成

```python
# app/services/predict_service.py
PREDICT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位资深技术面试官。
基于 JD 和定制版简历，预测面试可能被问到的高频问题。

要求:
- 每个问题按 STAR 法则给出参考回答
- key_points: 答题要覆盖的关键点
- hit_reason: 为什么会被问到（结合简历和 JD）
- category: 技术深度/项目经验/软技能/算法
- difficulty: EASY/MEDIUM/HARD

输出 {question_count} 道问题的 JSON 数组。"""),
    ("user", """JD:
{jd_text}

定制版简历:
{customized_resume}

预测面试题。"""),
])

class PredictService:
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
    
    async def predict(
        self,
        jd: Jd,
        customized_resume: CustomizedResume,
        question_count: int = 5,
    ) -> InterviewPrediction:
        result = await self.llm_service.structured_invoke(
            prompt_template=PREDICT_PROMPT,
            input_vars={
                "jd_text": jd.raw_text,
                "customized_resume": customized_resume.model_dump_json(),
                "question_count": question_count,
            },
            output_schema=InterviewPrediction,
        )
        return result
```

---

## 6. Celery 任务

```python
# app/tasks/customization_tasks.py
@celery_app.task(bind=True, max_retries=2, name="customize_resume")
def customize_resume_task(self, customization_id: int):
    async def _run():
        async with async_session() as db:
            customization = await db.get(Customization, customization_id)
            if not customization:
                return
            if customization.status == "COMPLETED":
                return  # 幂等
            
            # 乐观锁：抢占任务
            result = await db.execute(
                update(Customization)
                .where(Customization.id == customization_id)
                .where(Customization.status == "PENDING")
                .values(status="PROCESSING", started_at=datetime.utcnow())
            )
            if result.rowcount == 0:
                return  # 已被其他 worker 抢走
            
            await db.commit()
            
            try:
                service = CustomizationService(db, ...)
                await service.execute(customization_id)
            except Exception as e:
                if self.request.retries < self.max_retries:
                    customization.status = "PENDING"  # 重新可被抢
                    customization.error_message = str(e)[:500]
                    customization.retry_count += 1
                    await db.commit()
                    raise self.retry(exc=e, countdown=2 ** self.request.retries)
                else:
                    customization.status = "FAILED"
                    customization.error_message = str(e)[:500]
                    await db.commit()
                    log.error("customize_failed", 
                              customization_id=customization_id, error=str(e))
    
    asyncio.run(_run())
```

---

## 7. PDF 导出

```python
# app/utils/pdf.py
from weasyprint import HTML

CUSTOMIZATION_PDF_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: 'Microsoft YaHei', sans-serif; padding: 40px; }
  h1 { color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }
  h2 { color: #4CAF50; margin-top: 30px; }
  .section { margin-bottom: 25px; }
  .question { background: #f5f5f5; padding: 15px; margin: 10px 0; border-left: 4px solid #4CAF50; }
  .star { background: #fffbf0; padding: 10px; margin: 5px 0; }
  .score { font-size: 36px; color: #4CAF50; font-weight: bold; }
</style>
</head>
<body>
  <h1>定制化报告</h1>
  <p>JD: {{ jd.position }} @ {{ jd.company }}</p>
  <p>基础简历: {{ resume.original_filename }}</p>
  <p>生成时间: {{ generated_at }}</p>

  <div class="section">
    <h2>差距分析</h2>
    <p class="score">{{ gap.match_score }} / 100</p>
    <h3>已匹配技能</h3>
    <ul>{% for s in gap.matched_skills %}<li>{{ s }}</li>{% endfor %}</ul>
    <h3>缺失技能</h3>
    <ul>{% for s in gap.missing_skills %}
      <li><strong>[{{ s.priority }}]</strong> {{ s.skill }} - {{ s.reason }}</li>
    {% endfor %}</ul>
  </div>

  <div class="section">
    <h2>定制版简历</h2>
    <h3>{{ customized.summary }}</h3>
    <h3>技能</h3>
    <p>{{ customized.skills | join('、') }}</p>
    {% for exp in customized.experiences %}
      <h3>{{ exp.title }} @ {{ exp.company }}</h3>
      <p>{{ exp.duration }}</p>
      <p>{{ exp.description }}</p>
      <ul>{% for a in exp.achievements %}<li>{{ a }}</li>{% endfor %}</ul>
    {% endfor %}
  </div>

  <div class="section">
    <h2>面试预测</h2>
    {% for q in prediction.questions %}
      <div class="question">
        <p><strong>[{{ q.category }} / {{ q.difficulty }}]</strong> {{ q.question }}</p>
        <p><em>为什么被问到: {{ q.hit_reason }}</em></p>
        <div class="star"><strong>S:</strong> {{ q.star_answer.situation }}</div>
        <div class="star"><strong>T:</strong> {{ q.star_answer.task }}</div>
        <div class="star"><strong>A:</strong> {{ q.star_answer.action }}</div>
        <div class="star"><strong>R:</strong> {{ q.star_answer.result }}</div>
      </div>
    {% endfor %}
  </div>

  <div class="section">
    <h2>召回评估指标</h2>
    <p>混合策略 Recall@10: {{ retrieval.hybrid.recall_at_10 }}</p>
    <p>混合策略 Precision@10: {{ retrieval.hybrid.precision_at_10 }}</p>
  </div>
</body>
</html>
"""

def render_customization_pdf(customization: Customization) -> bytes:
    html = render_template(CUSTOMIZATION_PDF_TEMPLATE, {
        "jd": customization.jd,
        "resume": customization.base_resume,
        "gap": customization.gap_report,
        "customized": customization.customized_resume,
        "prediction": customization.prediction,
        "retrieval": customization.retrieval_metrics,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    return HTML(string=html).write_pdf()
```

---

## 8. 测试用例

```python
# tests/integration/tasks/test_customize_task.py
@pytest.mark.asyncio
async def test_customize_full_flow(sample_jd, sample_resume):
    # 1. 创建定制化
    service = CustomizationService(db, ...)
    c = await service.create(jd_id=sample_jd.id, resume_id=sample_resume.id)
    assert c.status == "PENDING"
    
    # 2. 执行（eager 模式同步跑）
    with celery_eager_mode():
        customize_resume_task.delay(c.id)
    
    # 3. 验证结果
    db.refresh(c)
    assert c.status == "COMPLETED"
    assert c.gap_report is not None
    assert c.customized_resume is not None
    assert c.prediction is not None
    assert c.retrieval_metrics is not None

# tests/unit/services/test_gap_analysis.py
@pytest.mark.asyncio
async def test_gap_analysis_with_mock_llm(mock_llm_service):
    mock_llm_service.structured_invoke.return_value = GapReport(
        match_score=75,
        matched_skills=["Java"],
        missing_skills=[MissingSkill(skill="Kafka", priority="HIGH", reason="JD 要求")],
        experience_gaps=[],
        recommended_focus=["补 Kafka 经验"],
    )
    
    service = GapAnalysisService(mock_llm_service)
    gap = await service.analyze(jd=mock_jd, resume=mock_resume)
    assert gap.match_score == 75
```

---

## 9. 面试讲点

1. **"定制化为什么要异步？"**
   > 涉及多次 LLM 调用（差距分析 + 定制 + 押题），单次 30-60 秒。同步阻塞用户体验差，Celery 异步 + 前端轮询体验好。

2. **"怎么保证定制化不重复消费？"**
   > 状态机 + 乐观锁。Worker 抢任务时把状态从 PENDING 改成 PROCESSING，rowcount=0 说明被抢走。

3. **"为什么定制简历后还要做押题？"**
   > 一站式服务闭环：用户拿到定制简历去投递，同时准备面试押题。减少用户多工具切换。

4. **"PDF 导出用 weasyprint 还是 iText？"**
   > Python 生态 weasyprint 优先：HTML 模板友好、C文支持、跨平台。Java 的 iText 在字体配置上坑多。

5. **"召回评估为什么要在定制化主任务里跑？"**
   > 用户能看到三种策略（向量/关键词/混合）的指标对比，体现"为什么用混合召回"。这是大数据挖掘岗位的核心问题。