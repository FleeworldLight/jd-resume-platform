# JD Resume Platform

这是一个本地优先的简历定制平台：后端用 FastAPI + SQLite，LLM 默认走 mock provider，前端直接用 Vite 启动，不依赖 Docker、Redis、Celery、Postgres 或外部服务。

> **在线演示**：https://fleeworldlight.github.io/jd-resume-platform/
> 演示站用的是脱敏样例数据（虚拟简历 + 真实岗位），并在 `DEMO_MODE` 下关闭了
> 上传 / 删除 / 抓取等写操作。完整功能请按下面的步骤本地运行。
>
> **不配任何 API Key 也能跑**：默认 mock provider 下，JD 结构化与定制化三步
> 都有本地规则兜底（见第 8 节），离线可用。

## 1. 目标

- Windows 本地双击打开即可运行
- 默认使用 SQLite，本地数据文件保存在 `backend/data/jd_platform.db`
- 默认启用爬虫，但可通过 `CRAWLER_ENABLED=false` 关闭
- 默认 LLM provider 为 `mock`，离线可用
- 保留 LangChain（OpenAI / Anthropic 真实接入仍可用）

## 2. 目录说明

- `backend/`：FastAPI 后端（`backend/data/` 存放本地数据库与简历文件）
- `frontend/`：React + Vite 前端
- `start.bat`：Windows 双击启动脚本
- `backend/.env.example`：环境变量示例（应用实际读取的是 `backend/.env`）
- `docs/`：设计文档（**先看 [docs/README.md](docs/README.md) 的状态索引**，部分文档写于旧架构阶段）
- `scripts/`：抓取 / 校验 / 去重脚本（用法见 [scripts/README.md](scripts/README.md)）
- `DEVELOPMENT_LOG.md`：每一轮改动、踩坑与验证结论（最详实的"为什么这么写"）

## 3. 一键启动（Windows）

在项目根目录直接双击运行：

```bat
start.bat
```

脚本会自动执行：

1. 创建 `backend/.venv`
2. 安装后端依赖
3. 安装前端依赖
4. 启动后端：`http://localhost:8000/docs`
5. 启动前端：`http://localhost:5173`

## 4. 手动启动

### 后端

```bat
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 前端

```bat
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

## 5. 环境变量

配置模板是 `backend/.env.example`，**必须先进 `backend/` 目录**再复制。

原因：`app/core/config.py` 里的 `env_file=".env"` 是相对路径，相对进程工作目录解析，而以 `start.bat` 方式启动时工作目录就是 `backend/`。根目录下的 `.env` 不会被读取。

```bat
cd backend
copy .env.example .env
```

默认示例已切换成 SQLite：

```env
DATABASE_URL=sqlite+aiosqlite:///./data/jd_platform.db
DATABASE_SYNC_URL=sqlite:///./data/jd_platform.db
LLM_DEFAULT_PROVIDER=mock
CRAWLER_ENABLED=true
```

> 注意：这里的 `./data/...` 是相对 `backend/` 的路径，即实际落在 `backend/data/`。

## 6. 本地开发与测试

### 后端测试

```bat
cd backend
.venv\Scripts\python.exe -m pytest tests/ -v
```

### 前端构建

```bat
cd frontend
npm run build
```

## 7. 数据位置

默认数据库文件：

```text
backend/data/jd_platform.db
```

简历原文件默认目录：

```text
backend/data/resumes/
```

## 8. LLM 模式

默认模式为 `mock`，无需 OpenAI / Anthropic Key 即可本地运行。

如果要接真实模型，可在 `LLM_DEFAULT_PROVIDER` 里切成 `openai` 或 `anthropic`，并填写对应 API Key。

> **没配 API Key 也能用哪些能力？**
>
> | 功能 | 默认（`mock`） | 配了真实 provider |
> |---|---|---|
> | 粘贴 JD → 结构化 | **规则抽取**（`heuristic_extract.py`），标记 `extract_mode=heuristic` | LLM，标记 `llm` |
> | 定制化 → 差距分析 | **技能集合比对**（`heuristic_pipeline.py`）：JD 要求 ∩ 简历体现，算覆盖度 | LLM 语义分析 |
> | 定制化 → 定制简历 | **只重排简历里已有的信息**，不编造经历 | LLM 重写 |
> | 定制化 → 面试押题 | 题目取自 **JD 原文句子**，STAR 只给「填空骨架」 | LLM 生成 |
>
> 规则模式下的结果都会在页面上用黄色横幅标注「当前结果是本地规则生成的」，
> 不会让人误以为是模型输出。
>
> **诚实边界**：规则模式不代写「我做了什么」这类经历——那属于编造履历。

## 9. 定制化模块说明

「定制化」页把一份简历和一条 JD 组合，跑一条流水线：

```
召回评估 → 差距分析 → 定制简历 → 面试押题
```

**选岗位**：页面顶部是**关键词搜索式**选择器（库里有 4800+ 条岗位，全量下拉不现实）。
输入关键词 → 拉取匹配的 20 条 → 点选即可。

**状态要求**：JD 处于 `PARSED` 或 `COMPLETED` 都可以发起；
`PENDING` / `PROCESSING` / `FAILED` 会被拦下并给出提示。

**报告包含**：

| 区块 | 内容 |
|---|---|
| 差距分析 | 匹配度（0-100）、已匹配技能、缺失技能（带 JD 原文证据 + HIGH/MEDIUM/LOW 优先级）、硬性条件差距、建议重点 |
| 定制版简历 | 匹配摘要、按岗位相关度排序的技能、从你简历里解析出的经历（含技术栈）、教育 |
| 面试预测 | 缺失技能→高压追问、已匹配技能→项目深挖、JD 职责原文→行为面；每题带「为什么被问到」与 STAR 骨架 |
| 召回评估 | hybrid / 纯向量 / 关键词三种策略的 Recall@K、Precision@K、NDCG@K |

> 库里只有 1 份简历时，召回指标恒为 1.0——因为 ground truth 就是它自己。
> 想看出差异需要多传几份简历。

**匹配度怎么算（规则模式）**：`round(100 × 已匹配技能数 / JD 要求技能数)`。
技能来自 `heuristic_extract.SKILLS` 词典（约 90 个技术关键词）+ JD 结构化字段。
如果 JD 里一个技能都识别不出来（纯业务岗），返回 0 并明确提示"无法计算"，不会瞎编。

## 10. 岗位数据抓取（可选）

内置牛客 / Boss 直聘的 JD 抓取能力，数据写入 `backend/data/jd_platform.db` 的 `jds` 表。

**网页端（「在招岗位」页）** 可以直接用：

- 右上角**「抓取最新岗位」** → 走牛客公开接口，几秒入库 60 条；输入框里有关键词时会带上该关键词检索
- **筛选栏**：关键词（岗位/公司/城市模糊匹配）、城市、学历、薪资区间、来源、排序、只看有薪资
- 岗位卡片支持**查看详情**（含职责 / 要求 / 原始 JD 全文）、**重新解析**、打开原岗位、删除
- 右侧可**粘贴 JD 文本**做结构化，或提交单个职位 URL 抓取

### 10.1 批量抓取

```bat
REM 牛客 + Boss，共 100 条
backend\.venv\Scripts\python.exe scripts\crawl_jobs.py --limit 100

REM 只抓牛客，走官方接口（推荐：1 次请求即可拿 100 条）
backend\.venv\Scripts\python.exe scripts\crawl_jobs.py --source nowcoder --limit 100

REM 只抓 Boss
backend\.venv\Scripts\python.exe scripts\crawl_jobs.py --source boss --query Python --city 100010000 --limit 50

REM 只取列表、不入库
backend\.venv\Scripts\python.exe scripts\crawl_jobs.py --source nowcoder --limit 20 --dry-run
```

| 参数 | 说明 |
|---|---|
| `--limit N` | 目标总条数（默认 100）；超过 300 需加 `--yes` |
| `--source nowcoder \| boss \| all` | 抓取来源 |
| `--nowcoder-mode api \| dom` | 牛客抓取方式；`api`（默认）走官方接口，`dom` 逐页渲染 |
| `--nowcoder-scope school \| full` | `school`=按招聘类型（去重约 450 条）；`full`=分类+关键词+多端点（**实测 4803 条**） |
| `--nowcoder-recruit-type` | 牛客招聘类型：数字、逗号分隔（如 `1,2`）、或 `all`（0/1/2/3 合并去重） |
| `--delay` | 请求间隔秒数（默认 1.5），**请勿设为 0** |
| `--structure` | 抓完后额外跑一次 LLM 结构化（默认关闭） |
| `--user-data-dir` / `--storage-state` | 复用已登录会话（Boss 需要） |

**全量抓取（推荐）**——走 `square-search` 的关键词检索，实测单次拿到 **4803 条去重职位**：

```bat
backend\.venv\Scripts\python.exe scripts\crawl_jobs.py --source nowcoder ^
  --nowcoder-scope full --limit 6000 --yes
```

> **为什么需要关键词检索？**
> `recruitType` 只有 `0/1/2/3` 返回不同数据（去重 447 条），填 `4~30` 都会回落到
> 与 `1` 相同的 200 条。真正能扩开数据量的是接口的 `query` 关键词参数
> ——26 个关键词就把去重总量从 447 推到 2581。`--nowcoder-scope full` 会用
> 107 个关键词种子逐个检索，并叠加 `/u/job/search`、`/u/job/list` 两个列表端点，
> 连续 15 个关键词无新增时自动停止。实测耗时约 3.5 分钟、250 次低频请求
> （默认 0.35s 间隔），得到 **4803 条唯一职位**。

> **薪资单位说明**：牛客有两种薪资口径，由 `salaryType` 区分（实测 100% 对应）——
> `2` 为月薪（K/月），`1` 为日薪（元/天）。`salary_min/salary_max` 两列在系统里
> 按「月薪 K」呈现，因此**日薪岗位的数值列留空**，原始文本存在
> `structured.crawl_meta.salary_display` 并写入正文，避免出现「500-550K」这类误导值。

### 10.2 清理重复行

```bat
REM 预览（默认不改数据）
backend\.venv\Scripts\python.exe scripts\dedupe_jds.py

REM 确认后执行
backend\.venv\Scripts\python.exe scripts\dedupe_jds.py --apply
```

### 10.3 校验数据真实性

抓完后建议跑一次校验：它会**独立打开每个职位的真实详情页**，
从页面内嵌数据里取出站点自己渲染的字段，与库中记录逐字段比对
（职位名、公司 ID、薪资、城市、学历、正文），确认没有脏数据。

```bat
REM 静态校验（全量、不联网）
backend\.venv\Scripts\python.exe scripts\verify_jds.py

REM 抽样 15 条联网比对真实页面
backend\.venv\Scripts\python.exe scripts\verify_jds.py --live 15

REM 全量联网比对（约 4-5 分钟）
backend\.venv\Scripts\python.exe scripts\verify_jds.py --all-live
```

### 10.4 Boss 直聘说明（重要）

**当前环境下 Boss 无法抓取**，排查结论如下：

- 其搜索接口对无会话访问统一返回 `{"code":35,"message":"您的IP地址存在异常行为."}`。
  实测更换 `Accept` / `Referer` / `Origin` / `X-Requested-With` 等请求头**均无效**，
  判定发生在 IP / 会话层，不是请求头能解决的。
- Boss 的 `robots.txt` 明确 `Disallow: /*?query=*`、`*?city=*`、`*?experience=*` 等，
  **不欢迎对搜索结果做抓取**，并专门封禁了 `Jobuispider` 这类职位爬虫 UA。
- 官方开放平台（`hi-open.zhipin.com`）面向**企业招聘方**，需创建应用、申请权限、
  申请 IP 白名单，**没有面向求职者的职位搜索接口**。

唯一有技术希望的路子是**复用你自己账号的登录态**：

```bat
REM 1) 检查依赖与配置（不开浏览器）
backend\.venv\Scripts\python.exe scripts\boss_login.py --check

REM 2) 打开浏览器手动登录，脚本自动检测能否看到职位并保存会话
backend\.venv\Scripts\python.exe scripts\boss_login.py

REM 3) 小批量验证（先别全量）
backend\.venv\Scripts\python.exe scripts\crawl_jobs.py --source boss ^
  --storage-state backend\data\boss_state.json --limit 10 --dry-run
```

> **请自行评估风险**：用账号低频抓取仍与 Boss 的 robots 条款存在张力，
> 最坏情况是账号被风控。建议只抓自己求职真正需要的岗位。
>
> 项目**不做任何绕过**：不轮换 IP、不破解 `__zp_stoken__` 签名、不伪造浏览器指纹。

### 10.5 已知限制

- **牛客**：可用，走官方接口，速度快。
- **Boss 直聘**：见 10.4，需自备登录态且存在条款风险。
- 请遵守目标站点的 robots 与服务条款，仅用于个人求职分析，保持低频访问。

## 11. 部署到线上（公开演示）

部署**自动分两种模式**，由仓库变量 `VITE_API_BASE` 是否配置决定：

| 模式 | 触发条件 | 效果 |
|---|---|---|
| **纯静态演示** | 没配 `VITE_API_BASE`（默认） | 前端读 `frontend/public/demo-data/*.json`，**不需要任何后端**。岗位可筛选/分页/看详情、简历可看、定制化报告可看；写操作会给出友好提示 |
| **连接真实后端** | 配了 `VITE_API_BASE` | 全部功能可用（抓取、上传、跑新定制化…） |

也就是说：**什么都不配、直接 push，Pages 上就已经是一个可用的演示站**。
这样后端还没部署时也不会看到白屏。

| 部分 | 托管 | 说明 |
|---|---|---|
| 前端 | **GitHub Pages** | 由 `.github/workflows/deploy.yml` 自动构建发布 |
| 后端（可选） | 支持 Docker 的平台（见 11.2 的对比表） | 需要长驻进程；Pages 跑不了 Python |

### 11.1 前端（GitHub Pages）

1. 仓库 **Settings → Pages → Source** 选 **GitHub Actions**
2. **Settings → Secrets and variables → Actions → Variables** 添加 `VITE_API_BASE`
   = 后端地址（如 `https://xxx.onrender.com`，**不要带结尾斜杠**）
3. push 到 `main` 即自动构建发布，地址形如 `https://<用户名>.github.io/<仓库名>/`

构建时注入两个变量（见 `.github/workflows/deploy.yml`）：

- `VITE_BASE=/<仓库名>/` —— 子路径部署必需，否则静态资源全部 404
- `VITE_API_BASE` —— 跨域必须用绝对 URL

深链接（例如直接刷新 `/jds`）靠构建后把 `index.html` 复制成 `404.html` 兜底。
若仓库变量没配，工作流会打印 warning，前端会显示"后端暂时连不上"并给出重试按钮。

### 11.2 后端

用 `backend/Dockerfile`，任何支持 Docker / 长驻进程的平台都能跑。

> **先看一个现实**：免费额度够用、又能在大陆直接访问的平台很少。下面这张表是实际核对过的
> （不同时期政策会变，注册前请以官网为准）：

| 平台 | 有免费计算资源吗 | 大陆可访问性 | 备注 |
|---|---|---|---|
| 阿里云函数计算 FC | 有（按量计费，闲置近乎免费） | ✅ 最稳 | Serverless，需实名；原生支持 FastAPI |
| 腾讯云 CloudBase / SCF | 有（免费版需领兑换券） | ✅ 稳定 | 需实名，微信/QQ 扫码登录 |
| Render | 有（Web 服务 750 小时/月） | ⚠️ 控制台与 `onrender.com` 有时不稳 | 闲置 15 分钟休眠，冷启约 60s |
| Hugging Face Spaces | 有（免费 CPU 档） | ❌ 大陆常无法登录 | — |
| Zeabur | **没有** | 后台中文、访问较快 | 注意：$0 计划**只能管理自有服务器**，跑服务需 $5/月 |
| Vercel | 有 | ⚠️ 不稳 | Serverless 无持久文件系统 + 单请求 60s 超时，**本项目的 SQLite 方案不适用** |

> **如果只是要一个"能看的演示"，不部署后端反而更划算**：把数据导出成静态 JSON 交给
> Pages 直接托管——零平台依赖、不休眠、大陆打开更快。代价是抓取 / 上传 / 新跑定制化不可用
> （这些在 `DEMO_MODE` 下本来也关了大部分）。

> **完整的 Hugging Face Spaces 部署步骤**（建 Space、令牌、环境变量、常见报错）见
> [docs/deploy-huggingface.md](docs/deploy-huggingface.md)；
> 用 `scripts/prepare_hf_space.py` 可以一键生成符合 HF 要求的仓库目录。

选定平台后的步骤：

1. 用 `backend/Dockerfile` 构建 —— Hugging Face Spaces 需要把 `backend/` 的内容推到
   Space 仓库根目录（HF 要求 Dockerfile 在根）；Render 则把 Root Directory 填 `backend`
2. 配置下面的环境变量
3. 拿到分配的公网域名，填进 GitHub 仓库变量 `VITE_API_BASE`（见 11.1）

需要配置的环境变量：

| 变量 | 值 | 说明 |
|---|---|---|
| `SECRET_KEY` | 32+ 字节随机串 | `python -c "import secrets;print(secrets.token_urlsafe(32))"` |
| `CORS_ORIGINS` | `["https://<用户名>.github.io"]` | **JSON 数组**写法；origin 只到 host，**不带路径** |
| `DEMO_MODE` | `true` | 打开演示守卫 |
| `CRAWLER_ENABLED` | `0` | 云端不提供逐页渲染抓取 |
| `LLM_DEFAULT_PROVIDER` | `mock` | 离线规则兜底，演示无需 API Key |

> 镜像里**不安装 Playwright 浏览器**：省内存，且云端 IP 抓岗位本就会被风控。
> 走 httpx 的公开接口抓取仍然可用。

### 11.3 数据为什么不会丢

免费平台的磁盘是临时的（重建/重启即清空）。仓库里带了脱敏种子库
`backend/seed/demo_seed.db`（4800+ 条岗位），`app/db/init_db.py` 在数据文件不存在时
**直接复制它** —— 冷启动即还原，比逐条 INSERT 快得多。

重新生成种子库（内置 PII 闸门，命中敏感词就不产出）：

```bat
backend\.venv\Scripts\python.exe scripts\export_demo_seed.py
```

### 11.4 演示模式做了什么

`DEMO_MODE=true` 时，非 GET 请求**只放行"纯计算"类操作**，其余返回 403：

| 放行 | 拦截 |
|---|---|
| 粘贴 JD → 结构化 | 所有 `DELETE` |
| 发起定制化 / 重试 | 上传简历（公开站绝不能允许匿名上传文件） |
| 按已抓取的原文重新解析 | 抓取岗位、改模型配置 |

前端读 `/health` 的 `demo_mode` 字段，在顶部显示黄色横幅告知访客哪些操作被关闭。

### 11.5 纯静态演示模式（无后端）

GitHub Pages 只能托管静态文件，跑不了 FastAPI。为了让演示站不依赖任何后端，
把后端数据**预导出成 JSON**，前端加一层「离线数据源」在浏览器里应答请求：

```
frontend/public/demo-data/
  health.json            健康检查（demo_mode=true）
  jobs.json              4825 条岗位（JD 正文截断到 300 字）
  facets.json            筛选项计数（城市/学历/来源/薪资区间）
  resumes.json           简历列表 + 详情
  customizations.json    定制化任务列表 + 报告详情
  llm-providers.json     模型配置（只读展示）
```

实现位置：`frontend/src/demoData.ts`（筛选/排序/分页逻辑照抄
`backend/app/services/jd_service.py`，保证与线上行为一致）+ `frontend/src/api.ts`
里的一处分流（`VITE_STATIC_DEMO=true` 时改走本地数据源）。

重新导出（数据更新后跑一次，产物需要提交进仓库）：

```bat
backend\.venv\Scripts\python.exe scripts\export_static_demo.py
```

体积参考：原始 JSON 约 6.8 MB，**gzip 后约 1.2 MB**；其中 `jobs.json` 只在进入
「在招岗位」页时才加载，首页只需约 5 KB。

**已知取舍**：静态模式下 JD 正文只保留前 300 字（文件里会附一句说明），
抓取 / 上传 / 发起新定制化不可用 —— 完整功能请本地运行或用真实后端。

## 12. 说明

- 当前版本已去掉 Docker / Redis / Celery / PostgreSQL 依赖
- 爬虫保留并默认启用，适合本地抓取 JD
- API 仍兼容统一 `Result` 响应格式，前后端交互保持一致
- 默认 `mock` provider 下，JD 结构化与定制化三步都有**本地规则兜底**，
  离线也能跑出可用结果；结果会标注 `extract_mode` 并在页面上提示

## 13. 参考与致谢

产品设计阶段参考了一个同类开源项目 **[LuJie CareerKit](https://github.com/Chozzc/Lujie-Careerkit)**（Apache-2.0，
中文名「录阶」）的思路，特此致谢。**仅借鉴设计理念，未复制其代码**——两个项目的技术栈与
架构都不同（对方是 Next.js + Prisma，本项目是 FastAPI + SQLite）。

明确借鉴的点记录在 `ROADMAP.md` 末尾，主要包括：

- 简历**多版本**机制（生成新版本而非覆盖原稿）
- AI 改动的**逐条审阅**（before/after + 逐项确认后才写回）
- 投递追踪的**阶段枚举与指标口径**（活跃流程、跟进日期默认 +7 天）
- 发给 LLM 前**剥离联系方式**，并在提示词里声明"已移除、不得诊断其缺失"

也有明确**不**照搬的地方（例如它的前端截图拼 PDF 方案，本项目用后端
reportlab + 内置中文字体，跨机器一致性更好），理由同样记在 `ROADMAP.md`。
