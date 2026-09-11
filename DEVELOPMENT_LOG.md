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
