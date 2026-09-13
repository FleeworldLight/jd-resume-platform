# 文档索引

> **代码即真相**：本目录部分文档写于旧架构阶段，内容可能与当前代码不一致。
> 当前架构的一句话概括：**FastAPI + SQLite + 同步流水线，LLM 默认 mock（离线规则兜底），无 Docker / Redis / Celery / Postgres。**
>
> 最新进展看仓库根目录的 `README.md` 与 `DEVELOPMENT_LOG.md`。

## 状态总览

| 文档 | 内容 | 状态 |
|---|---|---|
| [deployment/local.md](deployment/local.md) | 本地启动（start.bat / 手动） | ✅ 当前 |
| [architecture/error-handling.md](architecture/error-handling.md) | 异常体系与统一 `Result[T]` 响应 | ✅ 当前 |
| [modules/jd.md](modules/jd.md) | JD 模块（粘贴 / 抓取 / 结构化） | ✅ 当前 |
| [modules/llm-provider.md](modules/llm-provider.md) | LLM Provider 模块 | ✅ 当前 |
| [testing/strategy.md](testing/strategy.md) | 测试策略（venv / npm / pytest） | ✅ 当前 |
| [design.md](design.md) | 总体设计（最初版） | ⚠️ 部分过时 |
| [architecture/llm.md](architecture/llm.md) | LLM 调用规范 | ⚠️ 部分过时 |
| [architecture/retrieval.md](architecture/retrieval.md) | 召回引擎设计 | ⚠️ 部分过时 |
| [modules/customization.md](modules/customization.md) | 定制化模块 | ⚠️ 部分过时 |
| [modules/resume.md](modules/resume.md) | 简历模块 | ⚠️ 部分过时 |
| [deployment/acceptance.md](deployment/acceptance.md) | 验收标准 | ⚠️ 部分过时 |
| [testing/test-cases.md](testing/test-cases.md) | 测试用例清单 | ⚠️ 部分过时 |

## 「部分过时」是什么意思

这 7 篇写于项目采用 **Docker + PostgreSQL + pgvector + Redis + Celery** 的阶段。
那一整套已经被移除，与当前代码的对应关系：

| 旧文档里的说法 | 现在的实际实现 |
|---|---|
| Celery 异步任务（`app/tasks/`） | 已删除；抓取与定制化都是**同步执行** |
| PostgreSQL + pgvector 向量检索 | **SQLite**；向量存 `resume_vectors` 表（mock embedding 1024 维） |
| Redis / slowapi 限流 | 已删除 |
| Docker Compose 部署 | `start.bat` 双击启动（uvicorn + vite） |
| LLM 直连 OpenAI / Anthropic | 默认 **mock**，所有 LLM 功能都有**本地规则兜底**（`extract_mode=heuristic`） |

这些文档里的**业务规则、字段定义、流程设计大多仍然成立**（比如定制化流水线的阶段划分、
差距报告的字段），所以保留原文并在文首加了声明横幅，而不是直接删掉。
当面试材料或恢复旧架构时仍有参考价值；照着它们"修代码"则会踩空。

## 想快速了解现在的系统？

按这个顺序读：

1. 根目录 `README.md` —— 启动方式、数据位置、抓取与定制化的用法
2. `DEVELOPMENT_LOG.md` —— 每一轮改动、踩过的坑、验证结论（最详实）
3. `docs/deployment/local.md` —— 本地启动细节
4. `docs/modules/*.md` —— 各模块的字段与接口定义（注意过时声明）
