# 后端容器镜像（FastAPI + SQLite）
#
# 构建（在 backend/ 目录下执行，构建上下文就是 backend/）：
#   docker build -t jd-resume-backend ./backend
#   docker run -p 8000:7860 jd-resume-backend
#
# 部署到 Hugging Face Spaces（Docker SDK）：把 backend/ 里的内容推到 Space 仓库根目录即可，
# 因为 HF 要求 Dockerfile 位于 Space 仓库根。
# 部署到 Render：Root Directory 填 backend，它会用这个 Dockerfile。
#
# 注意：**不安装 Playwright 浏览器**。pip 装的只是 playwright 这个包，
# 没有 Chromium —— 逐页渲染抓取（Boss / 牛客 DOM）在容器里不可用是有意为之：
# 省内存，且云端 IP 抓取本就会被风控。走 httpx 的公开接口抓取仍然可用。

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 种子库会随镜像进入容器（backend/seed/demo_seed.db），
# app/db/init_db.py 在数据文件不存在时复制它，实现"重启后数据自动还原"
EXPOSE 7860

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
