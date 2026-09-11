# 验收标准

> **文档状态：部分过时（2026-09-11 标注）**
>
> 本文写于项目采用 Docker + PostgreSQL + pgvector + Redis + Celery 架构的阶段。
> 当前实际架构已简化为 SQLite + mock LLM provider + 无 Celery 的同步执行，详见根目录 README.md。
> 下文涉及 Docker / Postgres / pgvector / Redis / Celery / weasyprint 的段落仅作历史设计参考，不代表现状。

> 功能、性能、质量、演示四类共 44 条验收标准，每条都可勾选。

---

## 1. 功能验收（28 条）

### 简历管理

- [ ] **AC-R01**：上传 PDF/DOCX/TXT 简历，自动解析文本（3 秒内返回任务 ID）
- [ ] **AC-R02**：同一文件哈希重复上传，提示已存在，不重复入库（抛 RESUME_DUPLICATE 1003）
- [ ] **AC-R03**：简历删除后，相关定制化任务标记 FAILED（不直接删定制化，留痕）
- [ ] **AC-R04**：解析失败时返回明确错误信息，状态置 FAILED，可手动重试
- [ ] **AC-R05**：支持下载原文件（GET /api/resumes/{id}/file）

### JD 管理

- [ ] **AC-J01**：粘贴 JD 文本，5 秒内返回结构化结果（公司、岗位、薪资、技能、要求）
- [ ] **AC-J02**：JD URL 抓取异步执行，前端可轮询状态（PENDING → PROCESSING → PARSED → COMPLETED）
- [ ] **AC-J03**：抓取失败时记录错误信息，支持手动重试
- [ ] **AC-J04**：不同来源（牛客/Boss）字段填充正确
- [ ] **AC-J05**：不支持的网站（如 lagou）明确拒绝（抛 JD_SOURCE_UNSUPPORTED 2004），提示用户粘贴

### 定制化

- [ ] **AC-C01**：发起定制化任务后立即返回任务 ID（异步）
- [ ] **AC-C02**：定制化在 60 秒内完成（包含召回 + 3 次 LLM 调用）
- [ ] **AC-C03**：定制化报告包含完整四部分：
  - 差距报告（match_score + matched_skills + missing_skills + recommended_focus）
  - 定制简历（summary + skills + experiences + education）
  - 押题话术（默认 5 道，含 STAR）
  - 召回指标（Recall@10、Precision@10、NDCG@10）
- [ ] **AC-C04**：定制化任务失败可重试，重试不重复扣费
- [ ] **AC-C05**：定制化报告可导出 PDF，中文不乱码
- [ ] **AC-C06**：定制化任务有状态机保护，并发请求不会重复执行（乐观锁）

### 召回引擎

- [ ] **AC-RET1**：简历上传后 10 秒内向量化完成，可被召回
- [ ] **AC-RET2**：召回 TopK=50 时 P95 延迟 ≤ 500ms
- [ ] **AC-RET3**：混合策略召回率 ≥ 纯向量策略 + 纯关键词策略（任一）
- [ ] **AC-RET4**：评估指标可查（Recall@K、Precision@K、NDCG@K）
- [ ] **AC-RET5**：召回结果包含 matched_resumes 列表（Top10）

### 模型管理

- [ ] **AC-L01**：可新增 / 修改 / 删除 LLM Provider
- [ ] **AC-L02**：默认模型切换后立即生效，无需重启
- [ ] **AC-L03**：API Key 加密存储（Fernet），不在日志中明文出现
- [ ] **AC-L04**：LLM 调用失败时返回明确错误码（LLM_OUTPUT_INVALID 4007 等）
- [ ] **AC-L05**：测试连接接口可用（POST /api/llm-providers/{id}/test）

### 限流

- [ ] **AC-LIM1**：爬虫接口 2 QPS 限流，超限返回 429（限流错误码 -4）
- [ ] **AC-LIM2**：LLM 接口 5 QPS 限流，超限返回 429
- [ ] **AC-LIM3**：限流维度支持 IP（slowapi 默认 key_func=get_remote_address）

---

## 2. 性能验收（4 条）

- [ ] **AC-P01**：定制化任务端到端 P95 延迟 ≤ 60s（不计网络）
- [ ] **AC-P02**：召回 API P95 延迟 ≤ 500ms（含 embedding 计算）
- [ ] **AC-P03**：简历上传到向量化完成 ≤ 10s
- [ ] **AC-P04**：并发 10 个定制化任务，系统稳定（无 OOM、无任务丢失）

---

## 3. 质量验收（7 条）

### 代码规范

- [ ] **AC-Q01**：所有 Service 层异常都封装为 BusinessException（无裸 raise）
- [ ] **AC-Q02**：所有 LLM 调用走 LLMService.structured_invoke()（无业务代码裸调 LangChain）
- [ ] **AC-Q03**：所有 Prompt 模板外置到 app/prompts/*.py（无字符串拼接 Prompt）
- [ ] **AC-Q04**：所有外部调用（LLM/HTTP/爬虫）用 tenacity 加重试

### 测试

- [ ] **AC-Q05**：核心 Service 单测覆盖率 ≥ 85%，召回/评估算法 ≥ 90%
- [ ] **AC-Q06**：CI 卡线（GitHub Actions），覆盖率不达标不允许合并

### 文档

- [ ] **AC-Q07**：所有 API 有 OpenAPI 文档（FastAPI 自动生成，访问 /docs）

---

## 4. 演示验收（5 条）

> 面向面试演示场景，每条都可现场操作。

- [ ] **AC-D01**：能完整演示：上传简历 → 提交 JD → 发起定制 → 查看报告 → 导出 PDF
- [ ] **AC-D02**：能讲清楚混合召回原理（向量 0.6 + 关键词 0.4，归一化后加权）
- [ ] **AC-D03**：能讲清楚异步任务设计（Celery + Redis Stream + 状态机 + 乐观锁）
- [ ] **AC-D04**：能现场调取召回评估指标对比（向量 vs 关键词 vs 混合）
- [ ] **AC-D05**：能演示多 Provider 切换效果（设置页切换默认模型，下一次 LLM 调用立即生效）

---

## 5. 上线检查清单

部署到演示环境前，必须完成：

```
□ .env 已配置 LLM_API_KEY 和 LLM_ENCRYPTION_KEY
□ PostgreSQL 扩展已启用（pgvector + zhparser）
□ Alembic 迁移已执行（alembic upgrade head）
□ Docker Compose 一键启动成功
□ 后端健康检查通过（/health 返回 200）
□ 前端可访问（http://localhost）
□ Celery worker 已注册（celery -A app.tasks.celery_app inspect registered）
□ 至少 1 个 LLM Provider 已配置并设为默认
□ 测试连通性成功（POST /api/llm-providers/{id}/test）
□ 上传 1 份简历、提交 1 个 JD、完成 1 次定制化演示
```

---

## 6. 测试对照表

| 验收项 | 自动化测试 |
|---|---|
| AC-R01 | `test_upload_resume_*` |
| AC-R02 | `test_upload_resume_duplicate` |
| AC-R03 | `test_delete_resume_cascade` |
| AC-R04 | `test_parse_resume_mark_failed` |
| AC-R05 | `test_download_file` |
| AC-J01 | `test_create_from_text` |
| AC-J02 | `test_submit_url_nowcoder` + `test_poll_status` |
| AC-J03 | `test_crawl_fail` |
| AC-J04 | `test_crawl_nowcoder/boss` |
| AC-J05 | `test_submit_url_unsupported` |
| AC-C01 | `test_create_success` |
| AC-C02 | `test_full_flow_text_jd`（含耗时断言）|
| AC-C03 | `test_full_flow_*`（验证四部分完整）|
| AC-C04 | `test_task_retry_on_failure` |
| AC-C05 | `test_export_pdf` |
| AC-C06 | `test_task_idempotent` |
| AC-RET1 | `test_index_resume` |
| AC-RET2 | `test_hybrid_search_p95_under_500ms` |
| AC-RET3 | `test_hybrid_better_than_single` |
| AC-RET4 | `test_evaluate_full` |
| AC-RET5 | `test_full_flow_*`（验证 matched_resumes）|
| AC-L01 | `test_create/update/delete_provider` |
| AC-L02 | `test_set_default_clears_others` |
| AC-L03 | `test_encrypt_decrypt_api_key` |
| AC-L04 | `test_analyze_schema_validation` |
| AC-L05 | `test_test_provider` |
| AC-LIM1 | `test_crawl_rate_limit` |
| AC-LIM2 | `test_llm_rate_limit` |
| AC-LIM3 | `test_rate_limit_*` |
| AC-P01 | E2E 性能测试 |
| AC-P02 | `test_hybrid_search_p95_under_500ms` |
| AC-P03 | `test_index_resume_task` |
| AC-P04 | E2E 并发测试 |
| AC-Q01 | `test_business_exception_*` |
| AC-Q02 | 代码审查 + 单测覆盖率 |
| AC-Q03 | `test_prompt_renders` |
| AC-Q04 | 代码审查 |
| AC-Q05 | pytest --cov |
| AC-Q06 | GitHub Actions |
| AC-Q07 | 访问 /docs |

---

## 7. 验收流程

```
1. 开发完成
   ↓
2. 跑全部测试（pytest --cov）
   ↓
3. CI 通过 + 覆盖率达标
   ↓
4. 本地 Docker Compose 启动
   ↓
5. 按 §5 上线检查清单勾选
   ↓
6. 按 §4 演示验收清单走一遍
   ↓
7. 完成
```

---

## 8. 面试演示脚本（参考）

**场景**：演示给面试官看。

```
1. 开场（30 秒）
   "这是一个基于大数据的 JD-简历匹配与定制化求职系统。
    核心特色：pgvector 向量召回 + PostgreSQL 全文检索混合打分。"

2. 上传简历（30 秒）
   上传 PDF → 展示异步解析 → 展示向量化

3. 提交 JD（30 秒）
   粘贴 JD 文本 → 展示 LLM 结构化抽取 → 展示字段填充

4. 发起定制化（60 秒）
   点击定制 → 后台展示 Celery 任务执行 → 展示报告

5. 查看报告（90 秒）
   差距分析（match_score、missing_skills）
   定制简历（重写后的 summary、技能排序）
   押题话术（5 道题 + STAR）
   召回指标（三种策略对比）

6. 导出 PDF（30 秒）
   一键导出 → 中文不乱码

7. 切模型演示（30 秒）
   在设置页切换默认 Provider → 下一次定制化立即生效

8. 架构讲解（60 秒）
   异步流水线：解析 → 索引 → 召回 → 差距 → 定制 → 押题
   召回原理：向量 0.6 + 关键词 0.4 归一化加权
```

总时长约 6 分钟，可压缩到 3 分钟。