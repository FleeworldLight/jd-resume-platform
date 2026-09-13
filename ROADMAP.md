# 项目路线图：上线部署 + 迭代功能设计

> 分两部分：**Part 1 部署上线**（可立即执行）、**Part 2 后续迭代**（设计已定型，按需排期）。
> 参考项目分析见文末附录。**`Lujie-Careerkit-main/` 只读不改、不进 git。**

---

# Part 1：部署上线

## 1.1 结论先行

**做得到**，但有两个必须先接受的取舍：

| 限制 | 影响 | 对策 |
| --- | --- | --- |
| 免费平台磁盘是临时的，重启即清空 | SQLite 数据会消失 | 仓库内放**脱敏种子库**，启动时若库为空则秒级复制还原（不是逐条 INSERT） |
| 免费实例会休眠（冷启动 30~90s） | 访客首次打开转圈 | 前端「后端唤醒中」提示 + 定时保活 |

**必须关掉的能力**：云端 IP 抓岗位。Boss 已明确封禁；牛客从云 IP 有被限流风险。
但 `/api/jds/crawl-nowcoder` 走 **httpx 纯接口、不需要浏览器**，有机会保留；
走 Playwright 的路径（`/api/jds/url`、Boss）在云端必然不可用，会给出明确报错。

## 1.2 目标架构

```
访客浏览器
   │  https://<用户名>.github.io/jd-resume-platform/   ← GitHub Pages（静态前端）
   └─► https://<后端域名>                              ← 免费云容器（FastAPI + SQLite）
          启动时：空库 → 从 backend/seed/demo_seed.db 复制还原
```

## 1.3 阶段 0：仓库卫生（**必须先做**）

1. `.gitignore` 追加（**只加忽略，不移动、不修改 `Lujie-Careerkit-main/`**——参考资料，原地保留）：

```gitignore
# 第三方参考项目（97M，与本项目无关，永不提交）
Lujie-Careerkit-main/
Lujie-Careerkit-main.zip
```

2. 提交。

> 已确认 `frontend/dist/`、`backend/data/`、`.venv/`、`node_modules/`、`.workbuddy/` 都在 `.gitignore` 里 ✓
> 所以**真实简历（手机号/邮箱/GitHub/学校）不会被推上去**。

## 1.4 阶段 1：后端改造（6 处）

### ① `backend/app/core/config.py` —— 加演示开关

```python
# 演示模式：公开部署时打开，拦截破坏性写操作（详见 main.py 的白名单）
demo_mode: bool = False
```

### ② `backend/app/main.py` —— 演示守卫 + 健康检查扩展

`demo_mode=True` 时，非 GET/HEAD/OPTIONS **只放行白名单**，其余返回 403 + 友好提示：

| 放行（纯计算，演示核心） | 拦截（破坏性/高消耗） |
| --- | --- |
| `POST /api/jds/text`（粘贴 JD → 结构化） | 所有 `DELETE` |
| `POST /api/customizations`（发起定制化） | `POST /api/resumes`（**公开站绝不能允许匿名上传文件**） |
| `POST /api/jds/{id}/reparse` | `PUT /api/resumes/{id}` |
| `POST /api/customizations/{id}/retry` | `POST /api/jds/crawl-nowcoder`、`/api/jds/url` |
|  | `POST/PUT/DELETE /api/llm-providers/*` |

`/health` 返回体加 `demo_mode`、`crawler_enabled`（前端据此显示演示横幅）。

### ③ `backend/app/db/init_db.py` —— 空库时从种子库还原

在现有「建表 + seed mock provider」之前插入：

```python
# 空库（或首次部署）→ 从仓库内种子库复制，秒级还原演示数据
if not DB_FILE.exists() and SEED_FILE.exists():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SEED_FILE, DB_FILE)
```

### ④ `scripts/export_demo_seed.py`（新增）—— 导出脱敏种子库

- 读 `backend/data/jd_platform.db` → 写出 `backend/seed/demo_seed.db`
- 内容：
  - `jds`：**全部 4825 条**（约 13MB，含 raw_text，岗位详情要用）；**清空 `source_url`**（去掉爬虫追踪参数）
  - `resumes`：**1 份虚构简历**（假姓名/手机/邮箱/GitHub/学校），**不复制真实那条**
  - `customizations`：2 条样例报告（已验证不含你的姓名/手机/邮箱/GitHub）
  - `llm_providers`：mock 1 条；`resume_vectors` / `evaluation_logs`：留空
- **导出后自动跑 PII 扫描**：正则匹配手机号 / 邮箱 / 真实姓名 / 学校 / GitHub 用户名，命中即**报错退出、不生成种子库**。
  （最后一道闸门：宁可导出失败，也不能把隐私推上去）

### ⑤ `backend/Dockerfile` + `.dockerignore`（新增）

```dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 7860
CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
```

- `requirements.txt` **不用改**：`playwright` 只装 Python 包、**不跑 `playwright install`**，镜像里没有浏览器 → 省内存，逐页渲染能力自然不可用。
- `.dockerignore` 排除 `.venv/`、`data/`、`__pycache__/`、`tests/`。

### ⑥ CORS 已就绪（无需改代码）

已确认 `main.py` 里有 `CORSMiddleware`，`allow_origins=settings.cors_origins`，只需用环境变量设 `CORS_ORIGINS`（**JSON 数组**语法）。

## 1.5 阶段 2：前端改造（5 个文件）

| 文件 | 改动 |
| --- | --- |
| `frontend/vite.config.ts` | `base: process.env.VITE_BASE \|\| "/"`；build 时 `sourcemap: false`；**保留 dev proxy** |
| `frontend/src/api.ts` | `const BASE = import.meta.env.VITE_API_BASE ?? "";` |
| `frontend/src/main.tsx` | `<BrowserRouter basename={import.meta.env.BASE_URL}>` |
| `frontend/src/Layout.tsx` | 顶部演示横幅（读 `/health` 的 `demo_mode`）："演示站点：抓取/上传/删除已关闭，数据为脱敏样例" |
| `frontend/src/pages/Dashboard.tsx` | 后端不通的文案改掉：现在是"请双击 start.bat"，线上改成**"后端在唤醒中，免费实例休眠后首次请求约需 30~60 秒"** + 重试按钮 |

**SPA 深链接**：保留 `BrowserRouter`，CI 构建后 `cp dist/index.html dist/404.html`。
（退路：若实测有问题，改 `HashRouter`，URL 变 `/#/jds`。）

## 1.6 阶段 3：CI/CD（`.github/workflows/deploy.yml`，新增）

版本号已对照 **GitHub 官方文档核实**（2026-09）：`checkout@v6` / `configure-pages@v5` / `upload-pages-artifact@v4` / `deploy-pages@v4`。

```yaml
name: Deploy frontend to GitHub Pages
on:
  push: { branches: [main] }
  workflow_dispatch:

permissions: { contents: read, pages: write, id-token: write }
concurrency: { group: pages, cancel-in-progress: true }

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - name: Install
        working-directory: frontend
        run: npm ci
      - name: Build
        working-directory: frontend
        env:
          VITE_BASE: /jd-resume-platform/
          VITE_API_BASE: ${{ vars.VITE_API_BASE }}
        run: npm run build
      - name: SPA fallback
        run: cp frontend/dist/index.html frontend/dist/404.html
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v4
        with: { path: frontend/dist }

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

> `VITE_API_BASE` 用 **repository variable** 即可（不是密钥）。

## 1.7 阶段 4：上线步骤（**需要你本人操作**：我没有 `gh` CLI，也没有你的账号）

1. GitHub 新建 public 仓库 `jd-resume-platform`（不要勾 README/gitignore）
2. `git remote add origin https://github.com/<用户名>/jd-resume-platform.git` → `git push -u origin main`
3. 建后端服务（见下方选型）
4. 配后端环境变量：

| 变量 | 值 | 说明 |
| --- | --- | --- |
| `SECRET_KEY` | 32+ 字节随机串 | 现为 `change-me-in-production...` 占位值，必须换；生成：`python -c "import secrets;print(secrets.token_urlsafe(32))"` |
| `CORS_ORIGINS` | `["https://<用户名>.github.io"]` | list 字段用 **JSON 数组**；origin 只到 host，**不带路径** |
| `DEMO_MODE` | `true` | 打开演示守卫 |
| `CRAWLER_ENABLED` | `0` | 云端不提供逐页渲染抓取 |
| `LLM_DEFAULT_PROVIDER` | `mock` | 离线规则兜底，演示无需 API Key |

5. 加仓库变量 `VITE_API_BASE` = 后端域名 → push 触发 Pages 构建
6. 仓库 Settings → Pages → Source 选 **GitHub Actions**
7. （可选）UptimeRobot 每 25 分钟探 `/health` 防休眠

### 后端平台选型

| 平台 | 免信用卡 | 内存 | 休眠 | 备注 |
| --- | --- | --- | --- | --- |
| **Hugging Face Spaces（Docker）** ★推荐 | 是 | 免费档较大（2 vCPU/16GB 档） | 闲置约 48h | 我**从这个网络取不到 HF 文档**，额度请在创建页确认 |
| **Render Free Web Service** 备选 | 历来免卡 | **512MB** | 闲置 15min，冷启约 60s | 直连 GitHub 最省事；不用装浏览器，512MB 够用 |

两者共用同一个 `backend/Dockerfile`。**不推荐 Railway / Fly.io**（已无长期免费额度，要绑卡）。

## 1.8 风险与处理

| 风险 | 处理 |
| --- | --- |
| 冷启动 30~60s，访客以为挂了 | 前端提示 + 重试；保活探测 |
| 云端 SQLite 被重置 | 启动 seed 还原；访客新增记录会丢（演示站可接受） |
| 云端 IP 抓岗位被风控 | DEMO_MODE 拦截；数据由种子库提供 |
| SQLite 并发写锁 | DEMO_MODE 拦住绝大多数写 |
| `./data/` 相对路径 | 容器工作目录固定 `/app`，已被 seed 机制覆盖 |
| Pages 深链接 404 | `404.html` 复制法；退路 HashRouter |
| 公开仓库暴露源码 | `sourcemap: false` |
| 有人上传违法内容 | 上传接口被 DEMO_MODE 拦截 |

## 1.9 验收标准

1. `https://<用户名>.github.io/jd-resume-platform/` 打开，首页显示 4825 条岗位的真实统计
2. 「在招岗位」可搜索/筛选/翻页/看详情（含 JD 原文）
3. 「简历管理」能看到**虚构**简历，可查看与编辑
4. 「定制化」能选岗位 + 简历 → 发起 → 出报告（有「本地规则」提示）
5. 「抓取最新岗位」「上传简历」「删除」被拦截且提示友好
6. 全站零控制台错误；断后端时文案正确（不再提示"双击 start.bat"）
7. 仓库无 97M 第三方副本、无 `dist`、无 `data/`、无真实简历

### 本次需改动/新增的文件

**新增**：`backend/Dockerfile`、`backend/.dockerignore`、`backend/seed/demo_seed.db`（脚本生成）、`scripts/export_demo_seed.py`、`.github/workflows/deploy.yml`

**修改**：`.gitignore`、`backend/app/core/config.py`、`backend/app/main.py`、`backend/app/db/init_db.py`、`frontend/vite.config.ts`、`frontend/src/api.ts`、`frontend/src/main.tsx`、`frontend/src/Layout.tsx`、`frontend/src/pages/Dashboard.tsx`、`README.md`

**不动**：`requirements.txt`、业务 service、抓取模块、`docs/`

---

# Part 2：后续迭代（设计已定型，按需排期）

## 2.0 排期与依赖关系

```
P0 合规（LICENSE/致谢）
        │
部署上线 ─┴─► P1-1 简历版本 ──┬─► P1-3 逐条审阅（依赖版本）
                              │
                              └─► P1-2 投递追踪（独立，可并行）
                                        │
                                        └─► P2 隐私过滤 / 事实边界守卫
```

**理由**：P0 是公开仓库的合规底线；P1-1 修的是**现存缺陷**且改动最小，先做；
P1-3 必须建立在版本能力之上（"应用变更"要生成新版本）；P1-2 独立，可与任一并行。

## 2.1 P0｜公开仓库合规（成本极低）

| 事项 | 内容 |
| --- | --- |
| **加 `LICENSE`** | 当前仓库**没有许可证**——公开仓库在法律上等于"保留所有权利"，别人不能合法使用。建议 MIT |
| README「参考与致谢」 | 注明设计思路参考了 LuJie CareerKit（Apache-2.0）；声明**未复制其代码**，仅借鉴设计 |
| README 补密钥生成命令 | `python -c "import secrets;print(secrets.token_urlsafe(32))"` |

## 2.2 P1-1｜简历版本（修现存缺陷）

**问题**：`resume_service.update_text()` **原地覆盖** `resumes.resume_text`，改错了没有任何回退余地。

**关键约束（已核实）**：`resumes.content_hash` 是 `unique`，**不能**在原表上直接加版本行（同内容会撞唯一约束）；
SQLite 也**无法用 ALTER 删掉已有唯一约束**。
→ 因此**新建表**，不改原表结构（`create_all` 会自动建新表，**无需迁移脚本**）。

### 新增模型 `backend/app/db/models/resume_version.py`

```python
class ResumeVersion(Base, TimestampMixin):
    __tablename__ = "resume_versions"

    id: int
    resume_id: int        # FK → resumes.id，建索引
    text: str             # 该版本正文（Text）
    source: str           # upload | manual_edit | general_optimize | jd_tailored
    label: str            # 展示名：「原始上传」「手动编辑 2026-09-13」「定制：AI推理引擎」
    job_id: int | None            # 定制版本关联的岗位 FK → jds.id
    customization_id: int | None  # 由哪次定制化产出
    is_current: bool              # 当前使用中
    content_hash: str             # **不加 unique**，仅供"内容未变化"提示
```

### 兼容策略（关键）

`resumes.resume_text` **保留为"当前版本正文"的冗余缓存**。
这样 `export_bytes`、`_index_resume_embedding`、定制化（`base_resume_id`）、检索、种子脚本**全都不用改**，
只有"写入路径"改为同时落一条版本记录 → **渐进式、低风险**。

### 改动清单

| 文件 | 改动 |
| --- | --- |
| `backend/app/db/models/resume_version.py` | 新增模型 |
| `backend/app/db/models/__init__.py` | 注册模型（否则 `create_all` 不建表） |
| `backend/app/services/resume_service.py` | `update_text()` → **新建版本 + 更新缓存**；新增 `list_versions/create_version/restore_version`；`delete()` 连带删版本；上传解析成功后写初始版本 |
| `backend/app/api/resumes.py` | 新增 `GET /api/resumes/{id}/versions`、`POST /api/resumes/{id}/versions`、`POST /api/resumes/{id}/versions/{vid}/restore` |
| `frontend/src/pages/Resumes.tsx` | 编辑器顶部「版本历史」下拉 + 「回退到此版本」；保存按钮语义改为「保存为新版本」 |
| `frontend/src/types.ts` | 加 `ResumeVersion` 类型 |
| `scripts/export_demo_seed.py` | 虚构简历同时写一条初始版本 |

### 验收

上传 → 编辑保存 3 次 → 版本历史能看到 4 条 → 回退到第 2 版 → `resume_text` 与导出内容都变回第 2 版，**且原始上传文件仍可下载**。

## 2.3 P1-2｜投递追踪看板（新功能，产品感最强）

**缺口**：定制化跑完就结束，**没有"投出去之后"的环节**。补上它才真正闭环成"求职工作台"。

### 新增模型 `backend/app/db/models/application.py`

```python
class Application(Base, TimestampMixin):
    __tablename__ = "applications"

    id: int
    jd_id: int          # FK → jds.id，unique（一条岗位一条投递记录）
    resume_id: int | None          # 用哪份简历投的
    resume_version_id: int | None  # 用哪个版本投的（对接 P1-1）
    status: str         # APPLIED | ASSESSMENT | INTERVIEW | OFFER | REJECTED | ARCHIVED
    source: str | None  # 投递渠道：官网/Boss/牛客/内推…
    applied_at: datetime | None
    stage_date: datetime | None           # 当前阶段进入时间
    next_follow_up_at: datetime | None
    interview_round: int = 0
    notes: str | None
```

### 指标口径（纯函数，便于测试）→ `backend/app/services/pipeline.py`

- `is_active_pipeline_status(status)`：`APPLIED / ASSESSMENT / INTERVIEW` 计为**活跃**
- `get_application_action_date(app)`：优先 `next_follow_up_at` → 已投递但没填的按 **`applied_at + 7 天`** → 否则 `stage_date`
- `followups_due(apps, today)`：活跃 **且** action_date ≤ 今天
- `build_pipeline_summary(apps)`：`{submitted, active, followups_due, offers}` + 各阶段计数

### 改动清单

| 文件 | 改动 |
| --- | --- |
| `backend/app/db/models/application.py` | 新增模型 |
| `backend/app/schemas/application.py` | 请求/响应 schema |
| `backend/app/services/application_service.py` | CRUD + 调 `pipeline.py` 出统计 |
| `backend/app/api/applications.py` | `GET/POST /api/applications`、`GET/PUT/DELETE /api/applications/{id}`、`GET /api/applications/stats` |
| `backend/app/main.py` | 注册路由（**注意**：DEMO_MODE 白名单要放行 `POST/PUT /api/applications`，否则演示站没法体验） |
| `frontend/src/pages/Applications.tsx` | 新页面：看板视图（按阶段分列）+ 列表视图切换 |
| `frontend/src/App.tsx` / `Layout.tsx` | 注册路由与导航「投递看板」 |
| `frontend/src/pages/Dashboard.tsx` | 「资料库」旁加**投递漏斗**卡片（已投/活跃/待跟进/Offer） |
| `frontend/src/pages/Customizations.tsx` | 报告底部加「加入投递看板」按钮（预填 jd_id + resume_version_id） |

### 验收

定制化 → 加入看板 → 卡片进入「已投递」→ 拖到「面试」→ 阶段日期更新 →
Dashboard 漏斗联动 → 把跟进日期设为昨天，出现在「待跟进」。

## 2.4 P1-3｜AI 改动的逐条审阅（依赖 P1-1）

**现状**：定制化报告只能看，`customized_resume` 是一个整体对象，用户无法逐条取舍。
**目标**：每条变更独立勾选/编辑，**只把勾选的写回，且写回是新建版本、原稿不动**。

### 数据结构（加在定制化结果里）

```python
changes: list[{
    "id": "exp-0-title",
    "section": "experiences",              # summary/skills/experiences/education/highlights
    "field": "title",
    "item_label": "短视频平台内容分析系统",   # 便于界面定位
    "before": "……原简历原文……",
    "after": "……建议文案……",
}]
```

- **规则路径（mock）**：我们已有 `heuristic_pipeline._parse_resume()` 解析出的原始字段
  与 `customize_resume()` 产出的字段 → **两者做字段级 diff 即得 changes**，完全确定性、可复现。
- **LLM 路径**：沿用同一结构，由提示词要求输出；**或用同一套 diff 后处理**（更稳，不依赖模型听话）。

### 改动清单

| 文件 | 改动 |
| --- | --- |
| `backend/app/services/heuristic_pipeline.py` | 新增 `build_changes(original, customized)`（字段级 diff） |
| `backend/app/schemas/customization.py` | `CustomizedResume` 加 `changes: list[ResumeChange]` |
| `backend/app/services/customization_service.py` | 生成后组装 `changes` 并存库 |
| `backend/app/api/customizations.py` | 新增 `POST /api/customizations/{id}/apply`，body `{accepted_ids: [], edited: {id: value}}` |
| `backend/app/services/resume_service.py` | `apply_changes()` → 生成**新版本**（复用 P1-1），不覆盖原稿 |
| `frontend/src/pages/Customizations.tsx` | 「定制版简历」改为可勾选列表：每条 `原文 → 建议`，建议可编辑；底部「应用选中变更（生成新版本）」 |

### 验收

发起定制化 → 逐条勾选（含改一条建议文案）→ 应用 → 简历**新增一个版本**（标注来源该次定制化），
原版本内容**逐字节不变**；未勾选的变更不落库。

## 2.5 P2｜隐私过滤与事实边界守卫（接真实 LLM 之前必须做）

| 事项 | 设计 |
| --- | --- |
| **发 LLM 前脱敏** | 新增 `app/services/privacy.py::strip_contact(text)`：正则移除手机号 / 邮箱 / GitHub 链接；**所有 LLM 调用入口统一过一遍**。提示词里明确声明"联系方式已移除，不得诊断其缺失"（否则模型会提示"简历缺少邮箱"） |
| **事实边界守卫** | 新增 `app/services/llm_guard.py`：LLM 输出不得引入**原简历中不存在的实体**（学校/公司/项目/奖项/证书/技能/时间/数字）。做法：把原简历抽出的实体集合与 LLM 输出比对，出现新增实体则**拒绝写回并记录告警**。配合提示词形成三重兜底 |
| **哪些字段 AI 不许碰** | 学其思路：GPA、日期、联系方式等标为 `user-confirm`，即使 LLM 给了值也**不自动应用**，只在审阅界面提示用户自己填 |

## 2.6 P3｜待议（价值中等，先不动）

- 按岗位归档的资料库视图（`Job` 聚合简历版本/定制报告/面试材料 —— 依赖 P1-1、P1-2 完成后才有意义）
- GHCR 镜像发布 workflow（任何人可 `docker run` 跑完整应用）
- i18n（中英双语）与英文 README
- 后端 `ruff` 统一风格

---

# 附录：参考项目 `Lujie-Careerkit-main/` 借鉴清单（只读不改、不进 git）

## 值得学的（已并入 Part 2）

| 它的做法 | 位置 | 我们的对应设计 |
| --- | --- | --- |
| 简历多版本：`Resume 1:N ResumeVersion`，生成即 `create` 新行，原稿永不 update | `repository.ts:446/577/625` | **P1-1**（因 `content_hash` 唯一，改为独立表） |
| 逐条审阅：`{section,itemLabel,field,before,after}` + 勾选/编辑 + 只写回勾选项 | `resume-review.ts:27`、`resume-optimization-result.tsx:243` | **P1-3** |
| 投递追踪：status 枚举 + 纯函数指标（活跃 = APPLIED/ASSESSMENT/INTERVIEW；未填跟进日期按投递 +7 天） | `schema.prisma:74`、`pipeline.ts:113/117/127/138` | **P1-2**（口径直接照搬） |
| 发 LLM 前删 email/phone/links，并声明"不得诊断其缺失" | `ai/resume-snapshot.ts` | **P2** |
| 事实边界：提示词严禁新增实体 + `action="user-confirm"` 标签 + 后端校验 | `ai-service.ts:82-100`、`resume-diagnosis.ts:79` | **P2**（三重兜底） |
| 示例数据"移除"时先把用户数据改挂到替代岗位再删，避免误删 | `repository.ts:161-233` | 演进种子脚本时参考 |
| Apache-2.0 + `NOTICE` + `third-party/` 许可证副本声明 | `LICENSE`/`NOTICE` | **P0** |

## 明确**不**照搬

- **它的 PDF 导出**：前端 `domToPng` 截图 + `jsPDF` 拼页，中文依赖系统字体（换台机器可能变字体/发虚）。
  我们用**后端 reportlab + 内置中文字体**，跨机器更稳 → **保持现状**。
- **它没有 E2E 测试**（仅 Vitest 单测），而我们已有 Playwright 端到端脚本 → 这点我们更强。
- `next.config.ts` 未配 `output: standalone`、`docker-compose.yml` 无 healthcheck → 不必学。
