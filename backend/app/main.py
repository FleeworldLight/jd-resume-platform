"""FastAPI 入口。

本地极简版：SQLite 零外部服务；启动时自动建表 + seed mock provider。
"""
from __future__ import annotations

from contextlib import asynccontextmanager
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
        }
    )


@app.get("/", response_model=Result[dict[str, str]])
async def root() -> Result[dict[str, str]]:
    return Result.ok({"message": "hello jd-resume-platform"})
