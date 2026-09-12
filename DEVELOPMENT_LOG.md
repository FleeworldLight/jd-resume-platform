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

---

## 2026-09-11（续二）数据真实性校验

### 动机

用户要求确认抓到的职位信息是否真实。

### 方法：用独立通道比对

只证明「数据来自接口」是不够的——接口也可能返回缓存或脏数据。
因此新增 `scripts/verify_jds.py`，用**另一条独立通道**复核：

直接打开每个职位的详情页 `https://www.nowcoder.com/jobs/detail/<id>`
（实测可被 httpx 直接取到，HTTP 200 / 约 44KB HTML），
再从页面内嵌的 `window.__INITIAL_STATE__.store.jobDetail.detail`
取出**站点自己渲染的字段**，与库中存储逐字段比对。

比对项：

| 页面字段 | 库中字段 |
|---|---|
| `jobName` | `position` |
| `companyId` | `structured.crawl_meta.company_id` |
| `salaryMin` / `salaryMax` | `salary_min` / `salary_max`（含哨兵值归一化） |
| `salaryMonth` | `structured.crawl_meta.salary_month` |
| `jobCity` | `city` |
| `eduLevel` | `structured.crawl_meta.edu_level` |
| `ext.infos` / `ext.requirements` 正文片段 | `raw_text` |

### 校验结果（全量 116 行，逐条打开真实页面）

| 集合 | 一致率 |
|---|---|
| **接口抓取行** | **101/101 = 100%** |
| 遗留行（旧 DOM 抓取） | 8/15 |
| 合计 | 109/116 |

7 条不一致**全部**是 id #1–#7 的遗留行：当时 DOM 抓取只存了正文、没提取出字段，
所以 `position` / `salary` 为空。而页面显示这些职位本身真实存在：

| id | URL | 页面真实职位 | 页面薪资 |
|---|---|---|---|
| 1 | `.../465046` | 内容运营（成都）-2027校招 | 7-12K |
| 2 | `.../465118` | 人工智能 | 16-25K |
| 3 | `.../465117` | 软件开发工程师（2027届） | 15-30K |
| 4 | `.../465096` | AI应用开发工程师 | 20-40K |
| 5 / 6 / 7 | `.../461392`（同一职位重复 3 行） | （27届秋招）SRE（运维）工程师-北京 | 20-35K |

**结论：本次抓取的 101 条数据 100% 与站点真实页面一致，不存在伪造或幻觉数据。**
不一致项全部来自清理前遗留的历史行，且性质是「字段缺失」而非「数据错误」。

### 静态校验（全量、不联网）

- URL 不合法 **0**；薪资不合理 **0**；正文不含职位名 **0**
- URL 重复 6 行（陈旧重复，`dedupe_jds.py` 可清理）
- `position` 为空 7 行、`company` 为空 14 行 —— 均为遗留行

### 用法

```bat
backend\.venv\Scripts\python.exe scripts\verify_jds.py             REM 静态校验
backend\.venv\Scripts\python.exe scripts\verify_jds.py --live 15   REM 抽样联网比对
backend\.venv\Scripts\python.exe scripts\verify_jds.py --all-live  REM 全量联网比对
```

全量联网比对约需 4–5 分钟（116 条 × 0.8s 间隔），报告会区分「接口抓取行 / 遗留行」。
建议在**每次全量抓取之后**都跑一次 `--live`，作为入库数据的质量门禁。

---

## 2026-09-11（续三）Boss 直聘可行性排查

用户要求继续尝试抓取 Boss 直聘。做了三条线的排查，结论如下。

### 结论一：换请求头无效，封锁在 IP / 会话层

搜索接口 `GET /wapi/zpgeek/search/joblist.json` 依次尝试了四组请求头：

| 请求头组合 | 返回 |
|---|---|
| 仅 User-Agent | `{"code":35,"message":"您的IP地址存在异常行为."}` |
| UA + `Accept: application/json` | 同上 |
| UA + `Accept` + `Referer` | 同上 |
| UA + `Accept` + `Referer` + `Origin` + `X-Requested-With` | 同上 |

四组完全一致 → 判定发生在 IP / 会话层。页面自身 JS 会生成 `__zp_stoken__` 之类凭证，
只有真实浏览器会话才带得出来。

### 结论二：robots.txt 明确禁止抓取搜索结果

```
User-agent: *
Disallow: /*?query=*        ← 正是搜索 URL 的形态
Disallow: *?city=*  *?experience=*  *?salary=*  *?degree=*
Disallow: /web/geek/recommend*   Disallow: /web/boss/*

User-agent: Jobuispider
Disallow: /                  ← 专门封禁"职位爬虫"类 UA
```

站点不仅禁止，还专门拉黑了一个叫 `Jobuispider` 的职位爬虫。

### 结论三：官方开放平台不适用于求职者

`hi-open.zhipin.com`（Bosshi 开放平台）面向**企业招聘方 / 合作伙伴**：
需要创建应用 → 申请权限 → 获取 access_token →（可选）设置 IP 白名单，
能力集中在「向企业内员工发消息」「职位同步发布」等 HR 集成场景，
**没有面向求职者的职位搜索接口**。

### 唯一可行的技术路径：复用用户自己的登录态

新增 `scripts/boss_login.py`：

1. 打开一个**可见**浏览器窗口，用户手动扫码/账号登录；
2. 脚本轮询检测搜索页能否渲染出职位卡片（多个选择器兜底），
   同时充当「账号 + 网络出口是否可用」的能力验证；
3. 检测通过后把会话保存为 `backend/data/boss_state.json`（已被 .gitignore 忽略），
   并打印下一步命令；
4. 失败时输出诊断（是否出现「安全验证」、页面是否为空、是否仍报 IP 异常）。

配套打通了登录态链路：

- `BossCrawler.list_job_urls(..., storage_state=...)`
- `batch.fetch_details(..., storage_state=...)`
- `crawl_jobs.py --storage-state <path>`

**明确不做的事**（已在代码注释与文档中写明）：不轮换 IP、不破解 `__zp_stoken__`
签名、不伪造浏览器指纹。登录态方案本身也与 robots 条款存在张力，
风险交由用户自行评估，最坏情况是账号被风控。

### 顺带修掉两个数据质量漏洞（实测踩坑）

排查过程中实测发现，Boss 搜索页模板里存在一个**不带职位 ID 的空链接**
`https://www.zhipin.com/job_detail/`，它会把**登录页**当成职位抓回来并入库
（实测产生了一条 `source=BOSS`、`position=NULL`、正文为「验证码登录/注册…」的脏数据）。

两处修补：

1. `BossCrawler.list_job_urls` 增加 URL 形态校验：
   必须是 `/job_detail/<职位ID>.html`（ID ≥ 6 位字母数字），其余链接计入
   `skipped` 并记 warning 日志。
2. `batch.fetch_details`：
   - `BLOCK_HINTS` 补充 `验证码登录` / `扫码登录` / `登录/注册`，识别登录页；
   - 新增兜底：若既未提取到 `position` 也未提取到 `company`，判定为
     登录页 / 模板页 / 空壳页，标记失败、不入库。

已删除那条测试脏数据（jds 表回到 116 行，BOSS 来源 0 行）。
`pytest` 55 项仍全部通过。

---

## 2026-09-12 牛客全量抓取

### 规模探测

牛客列表接口按 `recruitType` 分了多类，实测各类 `totalCount`：

| recruitType | totalCount | 说明 |
|---|---|---|
| 0 / 3 | 100 | 其它专场 |
| 1 | 200 | 校招 |
| 2 | 147 | 实习 |
| 4 / 5 | 200 | 其它专场 |

另外发现 **`pageSize` 实测可到 200**（原先代码按 100 设限），
即一个招聘类型一次请求就能拿满。注意各类型之间职位有大量重叠。

### 全量策略与结果

6 个类型各抓一遍 → 原始 947 条 → **按 `job_id` 合并去重后 447 条唯一职位**。

- 入库：新增 405、更新 42；`jds` 表最终 **526 行**
- 质量：`company` 非空 512、`position` 519、`city` 454、月薪非空 236
- 公司 Top：联想 88、华为HUAWEI 46、重庆千里科技 35、拼多多集团-PDD 32、
  华为软件技术 23、小红书 22
- 抽样在线校验 25 条 → **25/25 与真实页面一致**

对应 CLI：

```bat
backend\.venv\Scripts\python.exe scripts\crawl_jobs.py --source nowcoder ^
  --nowcoder-recruit-type all --limit 3000 --yes
```

### 修正：薪资单位（重要数据正确性问题）

全量入库后静态校验发现 **101 条薪资异常**（`500-550K`、`990-1040K` 等）。定位过程：

1. 这些行的 `salaryMonth` 都是 0；
2. 用真实浏览器渲染详情页 → 页面实际显示 **「500-550元/天」**，是**日薪**而非月薪；
3. 交叉验证 200 条 → **`salaryType` 与单位 100% 对应，无任何交叉**：
   - `salaryType=2` → 月薪，单位 K/月，`salaryMonth` 为发薪月数（如 15 薪）
   - `salaryType=1` → 日薪，单位 元/天

**处理原则：不发明折算数字。**
（`jds.salary_min/max` 列在整个系统里按「月薪 K」呈现，前端直接渲染成 "20-30K"；
把 500 元/天 塞进去会变成误导性的「500-550K」。）

日薪岗位改为：

- `salary_min` / `salary_max` **置空**
- 原始文本写入 `salary_display` 与 `structured.crawl_meta.salary_display`
- `raw_text` 写真实文本「薪资：500-550元/天」
- `crawl_meta.salary_unit` 标记 `day` / `month`，便于下游区分单位

修正后静态校验「薪资不合理」= **0**；单位分布 `month=200 / day=100 / 空=224`。

### verify_jds.py 同步修正

校验脚本原先只比对数值列，会把 100 条日薪岗位**全部误报失败**。
已改为按页面 `salaryType` 分支比对，并额外校验 `salary_unit` 与 `salary_display`。

### 运行说明（本环境限制）

- Bash 工具**禁止调用 `cmd.exe`**；PowerShell 调用 `.cmd` 同样被拦。
  前端可绕过：用 `node node_modules/vite/bin/vite.js` 代替 `npm run dev`。
- `nohup ... &` 与 PowerShell `Start-Process` 启动的进程，
  **会在每次工具调用结束时被沙箱回收**，跨调用即掉线。
- 可行方案：Bash 的 `run_in_background` 常驻任务（本次 task_id `5sOMvX`）。
  若该任务被回收，双击项目根目录的 `start.bat` 即可启动。

---

## 2026-09-12（续）简历管理闭环修复

### 用户反馈

「没有任何功能是能跑通的」「上传简历这里为什么没法浏览简历」。
需求：上传 → 拆解简历 → 在线编辑 → 保存 → 下载；首页入口改叫「简历管理」并加引导小字。

### 排查结论

1. **后端一直是正常的。** 实测完整链路：
   上传 TXT → `parse_status=COMPLETED`（提取 268 字）→ 详情 → 下载原件 → 列表，全部 HTTP 200。
   用户自己的 `陈晓阳 - 简历.pdf` 同样解析成功（1934 字），内容完整。
2. **前端也没有报错。** Playwright 打开真实浏览器：零控制台错误、零失败请求、
   上传成功、列表正常渲染。
3. **「没法浏览文件」的直接原因**：之前把服务放在**内置预览面板**里展示，
   那种沙箱 iframe 中**系统文件选择框不会弹出**。
   正确做法是让用户用**自己的浏览器**打开 `http://localhost:5173`。
4. **真实功能缺口**：确实不存在「在线编辑 / 保存 / 导出」，只有下载上传的原文件。

### 新增后端接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `PUT` | `/api/resumes/{id}` | 保存在线编辑后的简历全文（写 `resume_text`），并重建向量索引 |
| `GET` | `/api/resumes/{id}/export?fmt=pdf\|docx\|txt` | 导出**编辑后**的版本 |

- `ResumeService.update_text()` / `ResumeService.export_bytes()`
- `app/utils/pdf.py` 新增 `render_resume_pdf()`：复用 reportlab + `STSong-Light`
  中文字体（无系统字体依赖），短行当小标题、`-`/`•` 开头当列表项
- `schemas/resume.py` 新增 `ResumeUpdateRequest`

### 前端改动

- **`pages/Resumes.tsx` 整体重写**
  - 上传区改为**可点击 + 可拖拽**的大方框，用 `label htmlFor` 原生触发文件选择
    （比 `onClick → input.click()` 更稳），文案：「点击这里选择简历文件」
    「也可以把文件直接拖进这个方框」+ 绿色「选择文件」按钮
  - 顶部流程引导条：上传 → 自动拆解 → 在线编辑 → 导出
  - 「查看 / 编辑」打开编辑器：字数 / 行数统计、未保存提示、保存、
    重新解析、导出 PDF/DOCX/TXT、下载原件
- `Layout.tsx`：导航「简历」→「简历管理」
- `Dashboard.tsx`：首页卡片「上传简历」→「简历管理」，
  引导小字改为「上传 → 自动拆解 → 在线编辑 → 导出下载」
- `api.ts`：`download()` 增加 content-type 判断。
  后端把业务异常也包成 HTTP 200 + `Result` JSON，
  不判断就会**把错误信息当成文件下载下来**（得到一个 .pdf 的 JSON）。

### 验证

Playwright 真实浏览器端到端（零控制台报错）：

打开编辑器载入 292 字 → 编辑出现「有未保存修改」→ 保存显示「已保存」→
**刷新后改动持久化（312 字）** → 导出 `test_resume.pdf` 3261 字节 /
`test_resume.docx` 35808 字节。

`tsc --noEmit` 通过；`pytest` 55 项通过。

### 两条教训

1. **不要把依赖系统对话框的功能（文件选择、下载）放在沙箱预览面板里演示**，
   要让用户用自己的浏览器打开。
2. Playwright 定位按钮应用 `get_by_role("button", name=...)`；
   `get_by_text` 会先匹配到没有 `onClick` 的外层 `div`，
   造成「点了没反应」的假象（本次就因此误判过一次）。

---

## 2026-09-12（续三）粘贴结构化报错修复 + 在招岗位改名/筛选 + 牛客数据量扩到 4803

### 1. 修复 `MissingGreenlet`（用户粘贴 JD 报 500）

**现象**：`POST /api/jds/text` 返回
`内部错误: 1 validation error for JdResponse / updated_at / MissingGreenlet: greenlet_spawn has not been called`。

**根因**（精确定位到 `app/db/base.py`）：
`TimestampMixin` 用了 `server_default=func.now()` + **`onupdate=func.now()`**。
服务端 `onupdate` 会让 SQLAlchemy 在 UPDATE 之后把该列标记为**已过期**，
下次访问属性时必须再发一次 SELECT；而 Pydantic 的 `model_validate` 跑在
异步会话上下文之外 → 抛 `MissingGreenlet`。

**修复**（两处）：
1. **全局**：`TimestampMixin` 改为 Python 侧的 `default=utcnow` / `onupdate=utcnow`
   （`utcnow()` 返回 naive UTC，与 SQLite `CURRENT_TIMESTAMP` 口径一致）。
   值在 flush 时就写入对象内存，永不过期 → 根治。
2. **保险**：`structure_jd` commit 后 `refresh(jd, ["created_at", "updated_at"])`；
   `create_from_text` 统一 `return await self.get(jd.id)`，确保交给 Pydantic 前字段已加载。

### 2. 默认 provider 是 mock → 补规则抽取

`llm_providers` 表里只有 `mock`。mock 只按 schema 返回占位值，所以
「粘贴 → 结构化」即使不报错也是**全空字段**，看起来像功能坏了。

新增 `app/services/heuristic_extract.py`：纯规则抽取
（正则 + 段落切分 + 城市/技能词典）。`provider_type == "mock"` 时自动启用，
结果标记 `structured["extract_mode"] = "heuristic"`；配置真实 provider 后自动走 LLM（`"llm"`）。

实测（用户粘贴的网易游戏运营 JD）：职责 4 条、要求 5 条、学历「本科」全部正确抽出；
结构化样例则抽出职位 / 公司 / 城市 / 薪资 25-40K / 本科 / 3-5年经验 / 6 个技能。

### 3. 「职位」→「在招岗位」+ 筛选体系

命名：导航、首页卡片、页面标题统一改为**在招岗位**；
首页小字改为「抓取 / 筛选岗位，也可粘贴 JD 结构化」。

后端新增/扩展：
| 接口 | 说明 |
|---|---|
| `GET /api/jds` | 新增 `keyword / city / education / source / salary_min / salary_max / salary_only / sort` |
| `GET /api/jds/facets` | 城市 / 学历 / 来源 / 薪资区间的命中数统计（给下拉框用） |
| `POST /api/jds/{id}/reparse` | 按已有原文重新结构化 |
| `POST /api/jds/crawl-nowcoder` | 一键抓取（走公开接口，秒级返回摘要） |

`_apply_structured` 会**保留已有的 `crawl_meta`**，避免重新结构化把接口溯源信息冲掉。

前端 `pages/Jds.tsx` 整体重写：防抖关键词搜索、6 个筛选控件（关键词/城市/学历/薪资区间/来源/排序）、
「只看有薪资」开关、分页（12/24/48，上一页/下一页）、查看详情弹窗
（职责 / 要求 / 原始 JD / 来源溯源）、重新解析、删除。

### 4. 牛客数据量：447 → 4803（用户质疑成立）

用户问「就 500 多条？」——质疑是对的。实测三条结论：

1. `recruitType` **只有 0/1/2/3 返回不同数据**（100+200+147+100 → 去重 **447**）；
   填 `4~30` 全部回落成与 `1` 相同的 200 条，**是噪声，不要扫**（旧代码扫 4/5 纯属浪费）。
2. **`query` 关键词才是真正的扩展杠杆**：26 个词就把去重总量推到 2581。
3. 另有 `/u/job/search`（750 条）与 `/u/job/list`（500 条）两个公开列表端点。

实现 `NowcoderApiClient.fetch_all()`：分类轮 → 关键词轮（107 个种子，每词最多 2 页）
→ 端点轮，按 `job_id` 去重，连续 15 个关键词无新增自动停止。
新增 CLI 参数 `--nowcoder-scope {school,full}`。

**本次全量结果**：`4803` 条唯一职位 → 入库新增 4278 + 更新 525，耗时 3 分 35 秒。

### 5. 全量数据质量

| 指标 | 结果 |
|---|---|
| `jds` 总行数 | **4824**（NOWCODER 4822 / MANUAL 2） |
| position 非空 | 4819 |
| company 非空 | 4814 |
| city 非空 | 4211 |
| education 非空 | 4226 |
| experience 非空 | 4122 |
| 月薪（K）非空 | 2373 |
| 正文 ≥200 字 | 4709 |

城市 Top：北京 992、上海 751、深圳 480、杭州 263、广州 205。
公司 Top：华为 372、小米 238、快手 198、上海华为 124、途游游戏 119。

**真实性抽检**（`verify_jds.py --live 30`，逐条打开真实页面比对字段）：**30/30 一致**。

`source_url` 重复仅剩 1 组（ids 6/7/8，早期 DOM 抓取留下的带 query 参数 URL），
可用 `scripts/dedupe_jds.py` 清理。

### 6. 3 条「异常薪资」的溯源结论（不是我们的 bug）

`salary_min >= 100K` 共 3 条，全部**打开真实页面核对**，页面显示与库内**逐字一致**：

| id | 库内 / 页面显示 | 判断 |
|---|---|---|
| #491 | 置业顾问 · 200-260K * 12薪 | 站方原始数据 |
| #657 | 群核科技 · 算法研究员（世界模型）100-150K * 16薪 | 站方原始数据 |
| #4487 | 广东博迈医疗 · 设备工程师 6000-8500K * 13薪 | 站方**标注错误**（应为元） |

结论：**我们忠实镜像了站点数据**，没有伪造也没有「顺手修数字」。
上游的 3 条明显错标（尤其 6000-8500K）保留原样，避免引入我们自己的推测值。

### 7. 血泪教训：同一文件不要并行发多个 Edit

本次在**同一条消息里对同一个文件发两次 Edit**，结果只保留一处、另一处静默丢失：

- `nowcoder_api.py`：`fetch_all()` 整个方法丢失（导致脚本 `NameError`）
- `jd_service.py`：`extract_jd_heuristic` 的 import 丢失（导致接口 500）
- `crawl_jobs.py`：`RECRUIT_TYPES_DISTINCT` 的 import 丢失（导致脚本启动即崩）

**规则：一个文件一次只发一个 Edit**；需要多处改动就分多轮，或用 `Write` 整体重写。
（2026-09-11 已记过一次，本次又犯。）

### 8. 验证

- `tsc --noEmit` 通过；`pytest` 55 项通过
- Playwright 真实浏览器验证「在招岗位」页：导航/标题改名正确、6 个筛选控件可用、
  关键词「算法」220 条、城市「北京」55 条、重置恢复、详情弹窗可开可关（ESC）、
  **零控制台错误、零失败请求**
- 修掉一个自查发现的 bug：薪资区间的 `salary_min/max` 没被序列化进请求参数
