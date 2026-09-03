"""结构化日志（structlog）。"""
from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.core.config import settings

# trace_id 上下文变量，便于跨函数追踪同一请求
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def new_trace_id() -> str:
    trace_id = uuid.uuid4().hex
    _trace_id_var.set(trace_id)
    bind_contextvars(trace_id=trace_id)
    return trace_id


def get_trace_id() -> str:
    return _trace_id_var.get()


def clear_trace_id() -> None:
    _trace_id_var.set("")
    clear_contextvars()


def setup_logging() -> None:
    """初始化 structlog + 标准 logging。

    设计文档 §9.1：所有日志带 trace_id。
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
