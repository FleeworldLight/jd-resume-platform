# 把后端部署到 Hugging Face Spaces

> 本文档面向本项目（FastAPI + SQLite 后端）。前端在 GitHub Pages，
> 后端跑在 HF Spaces 的免费 Docker 容器里。
>
> **前提提醒**：Hugging Face 在大陆可能无法直接访问（需要自备网络条件）。
> 如果实在上不去，见文末「备选平台」。

---

## 0. 为什么需要后端

前端（GitHub Pages）是纯静态的，默认走**静态演示模式**——不需要后端也能看完整界面。
部署后端之后才能用上这些能力：

- 抓取岗位（走牛客公开接口）
- 上传并解析真实简历
- 发起**新的**定制化（用你的简历实时跑流水线）
- 导出 PDF

也就是说这一步是「锦上添花」，不做也不影响演示站可用。

---

## 1. 准备账号与令牌

1. 注册 / 登录 https://huggingface.co
2. 右上角头像 → **Settings** → **Access Tokens** → **New token**
   - 权限选 **Write**（推送代码需要）
   - 名字随意，例如 `jd-resume-space`
3. **把 token 复制存好**（形如 `hf_xxxxxxxx`）——它只显示一次

---

## 2. 新建 Space

打开 https://huggingface.co/new-space ，按下表填写：

| 字段 | 填什么 | 说明 |
|---|---|---|
| Owner | 你的用户名 | |
| Space name | `jd-resume-backend` | 决定域名，见下 |
| License | 随意（如 `mit`） | |
| **Select the Space SDK** | **Docker** → **Blank** | 关键：必须是 Docker |
| Space hardware | **CPU basic · FREE** | 免费档够用（我们不装浏览器，内存占用低） |
| Visibility | **Public** | 私有 Space 的域名外部调不通（前端要跨域访问） |

创建后你的后端域名是：

```
https://<用户名>-<space名>.hf.space
```

> 注意是**连字符**（把 `/` 换成 `-`），不是斜杠。

---

## 3. 生成待推送目录（一条命令）

HF 要求 **Dockerfile 在仓库根目录**，而本项目的 Dockerfile 在 `backend/`；
它还需要一份带 YAML front-matter 的 `README.md` 来声明 SDK。与其手工拼，直接用脚本：

```bat
backend\.venv\Scripts\python.exe scripts\prepare_hf_space.py
```

它会在**仓库外**生成 `_hf_space/`（同级目录），内容 = `backend/` 的干净副本 + Space 专用
README，并校验 Dockerfile / requirements.txt / app/main.py / seed 种子库是否都在位。

---

## 4. 推送

```bat
cd "G:\期末及简历和别的项目\测试\_hf_space"
git init -b main
git remote add space https://huggingface.co/spaces/<用户名>/<space名>
git add .
git commit -m "deploy: backend container"
git push space main
```

推送时会提示输入用户名和密码：

- 用户名 = 你的 HF 用户名
- **密码 = 第 1 步存下的 Access Token**（不是登录密码）

推完后回到 Space 页面，它会自动开始构建（Build 标签页可以看到日志）。
首次构建约 3~6 分钟（要装 langchain、reportlab 这些依赖）。

---

## 5. 配置环境变量（**别跳过**）

Space 页面 → **Settings** → **Variables and secrets**：

| 名称 | 类型 | 值 | 说明 |
|---|---|---|---|
| `SECRET_KEY` | **Secret** | 32+ 字节随机串 | 生成：`python -c "import secrets;print(secrets.token_urlsafe(32))"` |
| `CORS_ORIGINS` | Variable | `["https://<用户名>.github.io"]` | **JSON 数组**写法；origin 只到 host，**不带路径** |
| `DEMO_MODE` | Variable | `true` | 拦截上传/删除/抓取等写操作 |
| `CRAWLER_ENABLED` | Variable | `0` | 容器里没装浏览器，逐页渲染抓取不可用 |
| `LLM_DEFAULT_PROVIDER` | Variable | `mock` | 离线规则兜底，不需要任何 API Key |

> `CORS_ORIGINS` 不配的话，前端跨域请求会被浏览器拦掉，表现为「后端连不上」。

改完变量后 Space 会自动重启（约 1 分钟）。

---

## 6. 验证后端

浏览器打开（或 curl）：

```
https://<用户名>-<space名>.hf.space/health
```

期望返回：

```json
{"code":0,"message":"ok","data":{"status":"ok","db":true,"demo_mode":true,"crawler_enabled":false}}
```

- `db: true` → SQLite 正常
- `demo_mode: true` → 演示守卫生效
- 想看接口文档：`/docs`

再随便试一个真实接口，确认种子数据在：

```
https://<用户名>-<space名>.hf.space/api/jds?page_size=3
```

应该返回 4825 条里的前 3 条（说明 `seed/demo_seed.db` 自动还原成功了）。

---

## 7. 把地址接到前端

1. GitHub 仓库 → **Settings → Secrets and variables → Actions → Variables** → New variable
   - Name: `VITE_API_BASE`
   - Value: `https://<用户名>-<space名>.hf.space`（**结尾不要加斜杠**）
2. 手动重跑一次部署：**Actions → Deploy frontend to GitHub Pages → Run workflow**
3. 构建日志里应出现 `连接真实后端 https://...`（而不是「回退到纯静态演示模式」）

之后前端就用真实后端了。

---

## 8. 常见问题

| 现象 | 原因与处理 |
|---|---|
| Build 失败在 `pip install` | 多半是网络抖动，Space 页面点 **Restart** 重跑一次 |
| 打开了但报 502 / 一直 Starting | 容器还在启动或崩溃了；看 Space 的 **Logs** 标签页 |
| `/health` 返回 `"db": false` | 种子库没进镜像；确认 `_hf_space/seed/demo_seed.db` 存在后重推 |
| 前端提示「后端暂时连不上」 | ① `CORS_ORIGINS` 没配或写错（要 JSON 数组、不带路径）② 免费实例休眠了，等 30~60 秒重试 |
| 第一次访问很慢 | 免费档闲置一段时间会休眠，冷启动要几十秒，属正常现象 |
| 数据被改乱了想复原 | Space → **Restart**，容器重建时会从种子库重新还原 |
| 想更新后端代码 | 重新跑 `prepare_hf_space.py`，再 `git add . && git commit && git push space main` |

### 关于「端口」

HF 会把容器端口通过环境变量 `PORT` 传进来（默认 7860）。本项目的 Dockerfile 已经写成
`--port ${PORT:-7860}`，一般不用动。若 Space 起不来且日志里提示端口不对，
在 Space 的 `README.md` front-matter 里确认 `app_port: 7860`（`prepare_hf_space.py` 已生成）。

### 关于「数据会不会丢」

免费档磁盘是临时的：重建 / 重启会清空。本项目对此有专门处理——
`backend/app/db/init_db.py` 在数据文件不存在时，从镜像内的
`seed/demo_seed.db` 直接复制还原（4800+ 条岗位，秒级完成）。
所以「数据丢失」对演示站不是问题，只是访客新增的记录会随重启消失。

---

## 9. 备选平台（HF 上不去的话）

| 平台 | 优点 | 代价 |
|---|---|---|
| 阿里云函数计算 FC | 国内访问最稳、原生支持 FastAPI、闲置近乎免费 | 需实名认证；Serverless 形态要按它要求配置启动方式 |
| 腾讯云 CloudBase / SCF | 国内稳定、微信扫码登录 | 需实名；免费版要关注公众号领兑换券 |
| Render | 直接连 GitHub 仓库、无需另开 Space 仓库 | 大陆访问时好时坏；免费实例闲置 15 分钟休眠 |

**用 Docker 部署任何平台时的要点都一样**：
Root Directory 指向 `backend/`（或用 `prepare_hf_space.py` 生成的目录），
配好上面那 5 个环境变量，把域名填进 `VITE_API_BASE`。
