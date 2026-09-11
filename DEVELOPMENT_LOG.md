# 开发日志

## 2026-09-03

### 已完成：本地双击启动版改造

1. 任务 1：重写项目说明文档为本地优先方案
   - 说明已从 Docker/Postgres/Redis/Celery 方案改为 SQLite + mock provider + Windows 双击启动。
   - 更新了根目录 [README.md](README.md) 的启动方式、环境变量、测试方式和本地数据位置说明。

2. 任务 2：新增 Windows 一键启动脚本
   - 新增 [start.bat](start.bat)。
   - 功能包括：
     - 创建后端 `.venv`
     - 安装后端依赖
     - 安装前端依赖
     - 自动启动后端和前端
     - 输出本地访问地址：
       - 后端：http://localhost:8000/docs
       - 前端：http://localhost:5173

### 额外完成项

- 完成后端依赖整理与修正，默认配置已切换到 SQLite。
- 修正日志兼容层，解决标准库 `logging` 与 structlog 风格用法冲突，避免启动时 `TypeError`。
- 验证后端测试：55 项全部通过。
- 验证前端构建：Vite 打包成功。
- 验证应用导入成功：FastAPI 应用对象可正常创建。

### 运行注意事项

- 若端口 8000 已被占用，后端会出现 `winerror 10048`，这是端口冲突，不属于业务代码错误。
- 可在启动命令中改端口，或先关闭占用进程后重试。

### 当前状态

- 项目已趋于稳定，具备本地开发与运行所需的最小依赖链路。
- 默认策略为：SQLite + mock LLM + 本地爬虫 + Windows 双击启停。

---

## 2026-09-11

### 项目梳理与清理

对仓库做了一次完整审计与清理，行动如下：

1. **移出无关项目**
   - `爬面经/`（小林coding 面经爬虫 + 离线站点）与平台无任何关系，已移出到上一级目录独立存放。

2. **删除过时部署残留**（Postgres / Redis / Celery / Docker 阶段产物）
   - `docker-compose.yml`、`docker-compose.dev.yml`
   - `DEPLOY-RAILWAY.md`
   - `scripts/init-postgres.sql`（pgvector + zhparser 初始化）
   - `backend/Dockerfile`、`frontend/Dockerfile`、`frontend/nginx.conf`
   - 前 6 项经 git 跟踪，可从历史找回；后 2 项为未跟踪文件，已删除。

3. **删除失效的交接文档**
   - 原 `NEXT_AI_TODO.md` 所列待办已全部落地（Celery / slowapi 引用清除、start.bat 已写、README 已重写），继续保留会误导后续开发，故删除；其中有长期价值的技术约定已迁入本文件（见下节）。

4. **文档与现状对齐**
   - `docs/deployment/local.md` 重写为本地启动方案（start.bat / venv / npm）
   - `docs/architecture/async-tasks.md` 删除（描述的是已移除的 Celery 架构）
   - `docs/testing/strategy.md` 重写（Poetry / pnpm / Testcontainers → venv / npm / SQLite 内存库）
   - 其余 7 篇深度绑定旧架构的设计文档（`design.md`、`architecture/llm.md`、`architecture/retrieval.md`、
     `modules/customization.md`、`modules/resume.md`、`deployment/acceptance.md`、`testing/test-cases.md`）
     保留原文（含面试讲点价值），但在开头加入「文档状态：部分过时」声明，避免误导。

5. **配置与路径口径统一**（重要）
   - 应用实际读取的配置文件是 `backend/.env`，而非根目录 `.env`。
     依据：`app/core/config.py` 中 `env_file=".env"` 是相对路径，相对**进程工作目录**解析，
     而启动时工作目录为 `backend/`。因此根目录 `.env.example` 永远不生效，已删除。
   - 数据库真实位置是 `backend/data/jd_platform.db`（同理，`./data/jd_platform.db` 相对 backend 解析）。
     根目录 `data/` 为历史遗留空壳，已删除；README 与 start.bat 的提示文案已同步修正。

6. **提交固化**
   - 历史上"极简化改造"未提交，本次先补 2 个快照 commit，再提交本轮清理。

### 承接自原 NEXT_AI_TODO.md 的技术约定（务必保留）

- **LangChain 仍在使用**：`langchain-openai` / `langchain-anthropic` 保留，未彻底移除。
  若后续追求更轻量，可改为直接拼装 message 并删除这两个依赖。
- **定制化接口已改为同步执行**：`POST /customizations` 请求会阻塞约 30–60 秒（原先由 Celery 异步处理）。
  前端 customizations 页面原有的轮询逻辑已无意义，需改为长 loading 态并放宽超时时间。
- **mock provider 的字段约束**：`mock` 类型调用 `structured_invoke` 时返回空 JSON，
  因此 GapReport 等 Pydantic schema 必须给 `default_factory=list/dict`；
  `match_score` 为必填字段，mock 必须返回 `0` 或等价默认值，否则校验失败。
- **Embedding 实现**：mock provider 使用 `FakeEmbeddings`，维度固定 1024。
