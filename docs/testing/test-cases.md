# 测试用例清单

> **文档状态：部分过时（2026-09-11 标注）**
>
> 本文写于项目采用 Docker + PostgreSQL + pgvector + Redis + Celery 架构的阶段。
> 当前实际架构已简化为 SQLite + mock LLM provider + 无 Celery 的同步执行，详见根目录 README.md。
> 下文涉及 Docker / Postgres / pgvector / Redis / Celery / weasyprint 的段落仅作历史设计参考，不代表现状。

> 完整测试覆盖，按模块组织。

---

## 1. 简历模块

### 1.1 单元测试

**`tests/unit/services/test_resume_service.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_upload_resume_success` | 上传有效 PDF | 成功入库，status=PENDING |
| `test_upload_resume_pdf` | 上传 PDF | 解析文本非空 |
| `test_upload_resume_docx` | 上传 DOCX | 解析文本非空 |
| `test_upload_resume_txt` | 上传 TXT | 解析文本非空 |
| `test_upload_resume_too_large` | 上传 11MB 文件 | 抛 RESUME_FILE_TOO_LARGE (1004) |
| `test_upload_resume_invalid_type` | 上传 .exe | 抛 RESUME_INVALID_TYPE (1005) |
| `test_upload_resume_duplicate` | 上传相同哈希 | 抛 RESUME_DUPLICATE (1003) |
| `test_upload_resume_no_text` | 扫描版 PDF | 抛 RESUME_PARSE_FAILED (1002) |
| `test_parse_resume_mark_completed` | 解析成功后 | status=COMPLETED |
| `test_parse_resume_mark_failed` | 解析失败 | status=FAILED, error_message 不为空 |
| `test_delete_resume` | 删除简历 | 文件删除 + DB 删除 |
| `test_delete_resume_cascade` | 删除有定制化的简历 | 定制化任务标 FAILED |
| `test_delete_resume_not_found` | 删除不存在的 | 无操作 |
| `test_get_resume_status` | 查询状态 | 返回 parse_status + parse_error |

### 1.2 集成测试

**`tests/integration/api/test_resume_api.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_upload_via_api` | POST /api/resumes | 201 + Result.ok |
| `test_list_via_api` | GET /api/resumes | 返回分页结果 |
| `test_get_via_api` | GET /api/resumes/{id} | 返回详情 |
| `test_delete_via_api` | DELETE /api/resumes/{id} | 204 |
| `test_download_file` | GET /api/resumes/{id}/file | 返回 PDF 二进制 |
| `test_reparse` | POST /api/resumes/{id}/reparse | 触发 Celery |

---

## 2. JD 模块

### 2.1 单元测试

**`tests/unit/services/test_jd_service.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_detect_source_nowcoder` | URL 含 nowcoder | 返回 NOWCODER |
| `test_detect_source_zhipin` | URL 含 zhipin | 返回 BOSS |
| `test_detect_source_unsupported` | URL 是 lagou | 抛 JD_SOURCE_UNSUPPORTED (2004) |
| `test_create_from_text` | 粘贴 JD 文本 | 同步抽取，status=COMPLETED |
| `test_create_from_url` | 提交 URL | 创建记录，触发异步 |
| `test_crawl_nowcoder` | 牛客 URL | 返回 raw_text |
| `test_crawl_boss` | Boss URL | 返回 raw_text |
| `test_crawl_fail` | 无效 URL | 抛 JD_CRAWL_FAILED |
| `test_structure_jd` | raw_text 已存在 | LLM 抽取 + 落库 |

### 2.2 集成测试

**`tests/integration/api/test_jd_api.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_submit_text_success` | POST /api/jds/text | 同步返回结构化 |
| `test_submit_url_unsupported` | POST /api/jds/url 不支持的网站 | 抛 2004 |
| `test_submit_url_nowcoder` | 提交牛客 URL | status=PENDING |
| `test_poll_status` | 轮询 /api/jds/{id}/status | 返回 crawl_status |
| `test_rate_limit` | 1秒内提交 5 次 URL | 第 4 次起 429 |
| `test_get_jd_list` | GET /api/jds | 返回分页 |

### 2.3 爬虫测试

**`tests/integration/crawler/test_crawlers.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_nowcoder_crawl_real` | 真实牛客 URL | raw_text > 100 字符 |
| `test_boss_crawl_real` | 真实 Boss URL | raw_text > 100 字符 |
| `test_nowcoder_crawl_invalid` | 无效 URL | 抛异常 |
| `test_ua_rotation` | 多次调用 | UA 不重复（采样验证）|

---

## 3. 召回引擎

### 3.1 单元测试

**`tests/unit/services/test_retrieval_service.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_normalize_scores` | 归一化 | 分数在 [0, 1] |
| `test_normalize_empty` | 空列表 | 返回空 |
| `test_normalize_all_zero` | 全为 0 | 保持 0 |
| `test_hybrid_merge` | 混合融合 | 加权求和正确 |
| `test_hybrid_dedup` | 同一 resume_id 多次出现 | 只保留一个 |
| `test_hybrid_empty` | 都没召回 | 返回空 |

### 3.2 集成测试

**`tests/integration/test_retrieval_pg.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_vector_search_pgvector` | 真实 pgvector 召回 | TopK 结果有序 |
| `test_keyword_search_tsv` | PG 全文检索 | 命中关键词 |
| `test_index_resume` | 简历向量化 | 写入 resume_vectors |
| `test_chinese_tokenization` | zhparser 分词 | 中文正确分词 |
| `test_hybrid_better_than_single` | 混合 vs 单一 | 召回率更高 |

---

## 4. 评估指标

**`tests/unit/test_evaluation.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_recall_at_k_all_hit` | 全召回 | recall=1.0 |
| `test_recall_at_k_partial` | 部分召回 | 0 < recall < 1 |
| `test_recall_at_k_none` | 没召回 | recall=0.0 |
| `test_precision_at_k` | 精确率 | 命中数 / 总数 |
| `test_ndcg_at_k_perfect` | 完美排序 | ndcg=1.0 |
| `test_ndcg_at_k_random` | 随机排序 | 0 < ndcg < 1 |
| `test_ndcg_at_k_reverse` | 完全反向 | ndcg=0.0 |
| `test_evaluate_full` | 完整评估 | 返回 EvalResult |

---

## 5. 定制化模块

### 5.1 单元测试

**`tests/unit/services/test_customization_service.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_create_invalid_jd` | JD 未完成抽取 | 抛 3004 |
| `test_create_invalid_resume` | 简历未解析 | 抛 3004 |
| `test_create_success` | 输入合法 | 创建 PENDING 任务 |
| `test_execute_full` | 执行定制化 | 3 个产物都有 |
| `test_execute_recall_failure` | 召回失败 | 抛异常 |
| `test_execute_gap_failure` | LLM 失败 | 抛异常 + 状态重置 |
| `test_get_status` | 状态查询 | 返回当前状态 |

**`tests/unit/services/test_gap_analysis.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_analyze_with_mock_llm` | Mock LLM 返回 | GapReport 字段完整 |
| `test_analyze_schema_validation` | LLM 返回非法 JSON | 抛 LLM_OUTPUT_INVALID |

**`tests/unit/services/test_customize.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_customize_no_fabrication` | Prompt 验证 | 不伪造经历 |
| `test_customize_with_gap` | 传入 gap_report | 输出包含 gap 修复点 |

**`tests/unit/services/test_predict.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_predict_default_count` | 默认 5 题 | 5 道问题 |
| `test_predict_star_structure` | STAR 字段 | 4 个字段都非空 |

### 5.2 集成测试

**`tests/integration/tasks/test_customize_task.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_task_runs_eager` | Eager 模式执行 | status=COMPLETED |
| `test_task_idempotent` | 重复执行 | 不会重复生成 |
| `test_task_retry_on_failure` | LLM 失败 | 重试 2 次 |
| `test_task_retry_exhausted` | 持续失败 | status=FAILED |

### 5.3 E2E 测试

**`tests/e2e/test_customization_flow.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_full_flow_text_jd` | 粘贴 JD + 上传简历 + 定制 | 完整报告 |
| `test_full_flow_url_jd` | URL 抓取 + 上传简历 + 定制 | 完整报告 |
| `test_export_pdf` | 导出 PDF | PDF 文件可下载 |
| `test_retry_failed` | 失败后重试 | 重新执行 |

---

## 6. LLM Provider 模块

### 6.1 单元测试

**`tests/unit/services/test_llm_provider_service.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_encrypt_decrypt_api_key` | 加密 + 解密 | 原值一致 |
| `test_mask_api_key` | 脱敏 | 首尾 4 位 + *** |
| `test_create_success` | 创建 Provider | 入库 |
| `test_create_invalid_type` | 未知 provider_type | 抛 LLM_PROVIDER_TYPE_UNKNOWN (4003) |
| `test_set_default_clears_others` | 设默认 | 其他都置 false |
| `test_get_default` | 查默认 | 返回 is_default=true |
| `test_test_connection_success` | Mock 成功 | success=True |
| `test_test_connection_failure` | Mock 失败 | success=False |

### 6.2 集成测试

**`tests/integration/api/test_llm_provider_api.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_list_providers` | GET /api/llm-providers | 列表 |
| `test_create_provider` | POST | 201 |
| `test_update_provider` | PUT | 更新 |
| `test_delete_provider` | DELETE | 删除 |
| `test_test_provider` | POST /{id}/test | 返回结果 |
| `test_set_default` | POST /{id}/set-default | 默认切换 |

---

## 7. 异常 + 限流

**`tests/unit/test_exceptions.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_business_exception_default_msg` | 用 ErrorCode 默认消息 | 正确 |
| `test_business_exception_custom_msg` | 自定义消息 | 覆盖默认 |
| `test_result_ok` | Result.ok() | code=0 |
| `test_result_error` | Result.error() | 错误码 |

**`tests/integration/test_rate_limit.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_crawl_rate_limit` | 爬虫 1 秒 3 次 | 第 3 次起 429 |
| `test_llm_rate_limit` | LLM 1 秒 6 次 | 第 6 次起 429 |

---

## 8. Prompt 模板

**`tests/unit/prompts/test_jd_extract_prompt.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_prompt_renders` | format_messages | 含 jd_text |
| `test_prompt_has_system` | 有 system 消息 | True |

**`tests/unit/prompts/test_gap_analysis_prompt.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_prompt_renders_with_vars` | 传入 jd/resume/gap | 全部填充 |

**`tests/unit/prompts/test_customize_prompt.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_prompt_no_fabricate_clause` | 含"不允许伪造" | True |

**`tests/unit/prompts/test_predict_prompt.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_prompt_includes_count` | 含 question_count | True |

---

## 9. Celery 任务

**`tests/integration/tasks/test_resume_tasks.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_parse_resume_task` | Eager 执行 | 简历解析 |
| `test_index_resume_task` | Eager 执行 | 向量化 |

**`tests/integration/tasks/test_jd_tasks.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_crawl_jd_task` | Eager 执行 | 抓取 |
| `test_structure_jd_task` | Eager 执行 | 结构化 |

---

## 10. PDF 导出

**`tests/unit/utils/test_pdf.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_render_customization_pdf` | 完整定制化数据 | PDF 字节流 > 1KB |
| `test_render_with_chinese` | 中文数据 | PDF 生成成功（不报错） |
| `test_pdf_includes_sections` | 验证包含 | 差距/定制/押题/评估 |

---

## 11. 加密工具

**`tests/unit/utils/test_encryption.py`**

| 用例 | 描述 | 预期 |
|---|---|---|
| `test_encrypt_decrypt` | 加解密 | 一致 |
| `test_invalid_key` | 错误密钥 | 抛异常 |
| `test_empty_string` | 空字符串 | 正常处理 |

---

## 12. 评估标准对照表

| 验收项 | 对应测试 |
|---|---|
| AC-R01 简历解析 | `test_upload_resume_pdf/docx/txt` |
| AC-R02 简历去重 | `test_upload_resume_duplicate` |
| AC-R03 删除级联 | `test_delete_resume_cascade` |
| AC-J01 JD 结构化 | `test_create_from_text` |
| AC-J02 异步抓取 | `test_submit_url_nowcoder` |
| AC-J04 来源校验 | `test_submit_url_unsupported` |
| AC-C01 异步发起 | `test_full_flow_text_jd` |
| AC-C02 60 秒完成 | `test_full_flow_*` (测耗时) |
| AC-C03 报告完整 | `test_full_flow_*` (验证字段) |
| AC-C04 重试 | `test_task_retry_on_failure` |
| AC-C05 PDF 导出 | `test_export_pdf` |
| AC-RET1 简历索引 | `test_index_resume` |
| AC-RET2 P95 延迟 | `test_hybrid_search_p95_under_500ms` |
| AC-RET3 混合优于单一 | `test_hybrid_better_than_single` |
| AC-RET4 评估指标 | `test_evaluate_full` |
| AC-L01 多 Provider CRUD | `test_create/update/delete_provider` |
| AC-L02 默认切换 | `test_set_default_clears_others` |
| AC-L03 API Key 加密 | `test_encrypt_decrypt_api_key` |
| AC-LIM1 爬虫限流 | `test_crawl_rate_limit` |
| AC-LIM2 LLM 限流 | `test_llm_rate_limit` |

---

## 13. 测试数据 Fixtures

**`tests/fixtures/`**

```
sample_resume.pdf           # 测试用 PDF 简历
sample_resume.docx          # 测试用 DOCX 简历
sample_resume.txt           # 测试用 TXT 简历
sample_jd.json              # 测试用 JD 结构化数据
sample_customization.json   # 测试用定制化结果
prompts/
  expected_jd_extract.json  # LLM 输出期望
  expected_gap.json
  expected_customize.json
  expected_predict.json
```

**生成 fixtures 的脚本**：

```python
# scripts/gen_fixtures.py
"""生成测试用 fixtures（手动跑一次）"""
import json

# 生成 sample_jd.json
jd = {
    "company": "示例科技有限公司",
    "position": "Java 后端开发",
    "salary_min": 25,
    "salary_max": 40,
    "city": "北京",
    "experience": "3-5年",
    "education": "本科",
    "skills": ["Java", "Spring Boot", "MySQL", "Redis", "Kafka"],
    "responsibilities": ["..."],
    "requirements": ["..."],
}

with open("tests/fixtures/sample_jd.json", "w", encoding="utf-8") as f:
    json.dump(jd, f, ensure_ascii=False, indent=2)
```

---

## 14. 运行命令

```bash
# 全部测试
pytest

# 单元测试
pytest -m unit

# 集成测试
pytest -m integration

# E2E 测试
pytest -m e2e

# 带覆盖率
pytest --cov=app --cov-report=html --cov-fail-under=80

# 慢速测试（性能）
pytest -m slow

# 指定文件
pytest tests/unit/services/test_retrieval_service.py

# 指定用例
pytest tests/unit/services/test_retrieval_service.py::test_hybrid_merge
```