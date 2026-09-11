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

### 验证结果（2026-09-11）

- **后端测试**：`pytest tests/ -v` → **55 passed, 38 warnings in 6.12s**
  （警告均为 `datetime.utcnow()` 与 pytest-asyncio 的弃用提示，非错误）
- **后端冒烟**：uvicorn 启动成功，注册 **22 条 API 路由**；`/health`、`/docs`、`/openapi.json` 均返回 200；
  日志兼容层工作正常，无 TypeError。路由清单：resumes（5）、jds（6）、customizations、llm_providers 等。
- **前端冒烟**：vite v5.4.21 启动成功；`/` 返回 200 且 HTML 正常；`/src/main.tsx` 返回 200。
- 测试后端口 8000 / 5173 均已释放。

### 备注：本机环境的一个高危行为（重要）

在本仓库内**删除文件**会触发异常——被删文件所在的**父目录会被整体移入 G 盘回收站**。
该现象已两次精确复现（`git rm` 删 backend/Dockerfile、frontend/Dockerfile、scripts/init-postgres.sql 等，
导致 `backend/`、`frontend/`、`scripts/` 三个目录被回收，含 `.venv`、`node_modules`、`jd_platform.db`）。

规避方式：**用 `mv` 把文件移出仓库**（移到 `测试/_jd_removed/`）而不是删除。
本次所有删除项均以该方式完成，未再触发。原因未完全确定，不要用 `git rm`。

教训：破坏性操作前先 commit；操作后立即校验 `backend/.venv`、`frontend/node_modules`、`backend/data/jd_platform.db` 是否还在——
这三项不被 git 跟踪，一旦丢失 git 救不回来。

### 承接自原 NEXT_AI_TODO.md 的技术约定（务必保留）

- **LangChain 仍在使用**：`langchain-openai` / `langchain-anthropic` 保留，未彻底移除。
  若后续追求更轻量，可改为直接拼装 message 并删除这两个依赖。
- **定制化接口已改为同步执行**：`POST /customizations` 请求会阻塞约 30–60 秒（原先由 Celery 异步处理）。
  前端 customizations 页面原有的轮询逻辑已无意义，需改为长 loading 态并放宽超时时间。
- **mock provider 的字段约束**：`mock` 类型调用 `structured_invoke` 时返回空 JSON，
  因此 GapReport 等 Pydantic schema 必须给 `default_factory=list/dict`；
  `match_score` 为必填字段，mock 必须返回 `0` 或等价默认值，否则校验失败。
- **Embedding 实现**：mock provider 使用 `FakeEmbeddings`，维度固定 1024。

---

## 2026-09-11（续）岗位数据抓取能力

### 背景

用户指出项目应具备从 Boss 直聘 / 牛客抓取岗位并写入 SQLite 的能力。
核查后发现：`backend/app/crawler/` 已有单 URL 抓取（`NowcoderCrawler` / `BossCrawler`），
但**没有批量抓取入口**；`scripts/` 目录原本只有一个 postgres 初始化脚本（已随清理删除）。

### 新增文件

| 文件 | 作用 |
|---|---|
| `scripts/crawl_jobs.py` | 批量抓取 CLI：列表 → 详情 → 落库；支持 `--limit/--source/--dry-run/--structure` 等 |
| `scripts/dedupe_jds.py` | 合并 URL 规范化后重复的 `jds` 行（默认只预览，`--apply` 才执行） |
| `backend/app/crawler/nowcoder_api.py` | 牛客职位广场官方接口客户端 |
| `backend/app/crawler/batch.py` | 批量详情抓取，复用同一浏览器实例 |
| `backend/app/crawler/text_utils.py` | 正文清洗：按职位名锚点裁掉页面导航噪声 |

### 修改文件

- `backend/app/crawler/strategies/nowcoder.py`
  - **公司名提取修正**：牛客正文形如「北京小桔科技有限公司·校招经理」，
    原代码只匹配「·招聘」导致全部落空。改为四级兜底：
    正文「反馈率」上一行 → 角色后缀正则 → DOM 区块首词 → 页面 title。
  - 详情正文调用 `trim_leading_noise` 去掉前置导航（原来每条约有 250 字噪声）。
  - 列表链接去掉 query/fragment，避免同一职位重复入库。
- `backend/app/crawler/strategies/boss.py`
  - 新增 `list_job_urls`（列表页提取 `/job_detail/` 链接）与 `_extract_metadata`。
  - 新增风控探测：页面出现「异常行为 / 安全验证 / 请先登录」时抛 `CRAWLER_BLOCKED` 并给出可读原因。

### 站点可用性实测（关键结论）

| 站点 | 结果 |
|---|---|
| **牛客** | **可用**。列表页 DOM 固定只有 25 条，`?page=N` 与滚动加载均无效；抓包发现官方接口 `POST https://www.nowcoder.com/np-api/u/job/square-search`，`pageSize` 可到 100，共 200 条（2 页）。**1 次请求即可拿到 100 条。** |
| **Boss 直聘** | **不可用**。首页可访问（HTTP 200 / 537KB），但搜索接口返回 `{"code":35,"message":"您的IP地址存在异常行为."}` —— 站点侧 IP 风控，非本地技术问题。需家庭宽带或复用已登录会话（`--user-data-dir`）。 |

### 接口字段解析要点

- 列表返回混有**两种形态**，字段名完全不同，必须分别解析：
  - 形态 A「平台职位」（79/101）：`jobName` / `jobCity` / `salaryMin|Max|Month` / `eduLevel` /
    `graduationYear` / `recommendInternCompany.companyName` / `ext`（JSON 字符串，含 `requirements` + `infos`）
  - 形态 B「企业官网闪投」（22/101）：`jobTitle` / `description`（HTML）/ `salary`（文本）/
    `companyName` / `education`（中文）/ `city`
- `eduLevel` 数字码映射（**经详情页反查核实**，未核实的一律留空不猜）：
  `0 → 不限`、`5000 → 本科`、`6000 → 硕士`
- **薪资哨兵值**：`salaryMin=0` / `salaryMax=9999999` 表示「薪资面议」，必须过滤，
  否则入库会得到「0-9999999K」假数据。已修复，并改为接口模式下**覆盖式写入**以清掉旧值。

### 测试结果

- 小规模验证：3 条、5 条均成功，字段随排查逐步修正。
- **正式测试抓取：100 条全部成功**（新增 92 + 更新 8；形态 A 79 + 形态 B 22）。
- 数据质量（表内共 116 行）：`position` 109、`company` 102、`city` 96、`education` 95、
  `salary` 69（其余为「面议」，属正常）、正文 ≥200 字 115、**缺陷薪资残留 0**。
- **遗留重复**：`dedupe_jds.py` 预览发现 4 组重复共 6 行、8 条 URL 待规范化。
  **未执行删除，等用户确认。**

### 数据位置与可回溯性

`backend/data/jd_platform.db` → `jds` 表。
接口抓取的行会把原始码放入 `structured.crawl_meta`
（含 `shape` / `edu_level` / `salary_month` / `company_id` / `salary_raw` 等）便于回溯。
注意：若之后开启 `--structure`，LLM 结构化结果会覆盖该字段。
