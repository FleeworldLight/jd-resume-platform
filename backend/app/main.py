"""FastAPI 入口。

本地极简版：SQLite 零外部服务；启动时自动建表 + seed mock provider。
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.customizations import router as customizations_router
from app.api.jds import router as jds_router
from app.api.llm_providers import router as llm_providers_router
from app.api.resumes import router as resumes_router
from app.core.config import settings
from app.core.exceptions import BusinessException, ErrorCode
from app.core.logging import get_logger, new_trace_id, setup_logging
from app.core.result import Result
from app.db.init_db import init_db
from app.db.session import close_db, engine

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("app.startup", name=settings.app_name, version=settings.app_version)
    await init_db()
    yield
    await close_db()
    logger.info("app.shutdown")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
    default_response_class=JSONResponse,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- 全局异常处理 ----------
@app.exception_handler(BusinessException)
async def business_exception_handler(_request: Request, exc: BusinessException):
    logger.warning("business.error", code=int(exc.code), message=exc.message)
    return JSONResponse(
        status_code=200,
        content=Result.fail(code=exc.code, message=exc.message, data=exc.data).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg = "; ".join(
        f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in errors
    )
    return JSONResponse(
        status_code=200,
        content=Result.fail(code=ErrorCode.INVALID_PARAMS, message=msg or "参数校验失败").model_dump(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(_request: Request, exc: Exception):
    logger.exception("http.error", error=str(exc))
    return JSONResponse(
        status_code=200,
        content=Result.fail(
            code=ErrorCode.INTERNAL_ERROR,
            message=f"内部错误: {exc}",
        ).model_dump(),
    )


# ---------- 中间件：trace_id ----------
@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    new_trace_id()
    logger.info("http.request", method=request.method, path=request.url.path)
    response = await call_next(request)
    return response


# ---------- 中间件：演示模式守卫 ----------
# 公开演示站不能让人删库、上传文件、刷抓取接口，但又希望访客能体验核心能力。
# 所以采用**白名单**：只有"纯计算"的写操作放行，其余非 GET 一律 403。
_DEMO_ALLOWED_WRITES: list[tuple[str, str]] = [
    ("POST", r"^/api/jds/text$"),                  # 粘贴 JD → 规则结构化
    ("POST", r"^/api/jds/\d+/reparse$"),           # 按已抓取的原文重新解析
    ("POST", r"^/api/customizations$"),            # 发起定制化（生成报告）
    ("POST", r"^/api/customizations/\d+/retry$"),  # 重试失败的定制化
]


@app.middleware("http")
async def demo_guard_middleware(request: Request, call_next):
    if settings.demo_mode and request.method not in ("GET", "HEAD", "OPTIONS"):
        path = request.url.path
        allowed = any(
            request.method == m and re.match(pattern, path)
            for m, pattern in _DEMO_ALLOWED_WRITES
        )
        if not allowed:
            logger.info("demo.blocked", method=request.method, path=path)
            return JSONResponse(
                status_code=403,
                content=Result.fail(
                    code=ErrorCode.FORBIDDEN,
                    message=(
                        "这是在线演示站点，为避免数据被破坏，"
                        "抓取岗位 / 上传简历 / 删除 / 修改模型配置等写操作已关闭。"
                        "完整功能请克隆仓库本地运行（见 README）。"
                    ),
                ).model_dump(),
            )
    return await call_next(request)


# ---------- 路由 ----------
app.include_router(resumes_router)
app.include_router(jds_router)
app.include_router(customizations_router)
app.include_router(llm_providers_router)


@app.get("/health", response_model=Result[dict[str, Any]])
async def health() -> Result[dict[str, Any]]:
    from sqlalchemy import text

    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.warning("health.db_failed", error=str(exc))

    return Result.ok(
        {
            "status": "ok" if db_ok else "degraded",
            "app": settings.app_name,
            "version": settings.app_version,
            "db": db_ok,
            # 前端据此显示"演示站"横幅、决定哪些按钮要置灰
            "demo_mode": settings.demo_mode,
            "crawler_enabled": settings.crawler_enabled,
        }
    )


@app.get("/", response_model=Result[dict[str, str]])
async def root() -> Result[dict[str, str]]:
    return Result.ok({"message": "hello jd-resume-platform"})
