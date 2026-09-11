"""日志：标准库 logging（去掉 structlog，Windows 本地更稳）。

注意：代码里大量 `logger.info("msg", key=value)` 是 structlog 风格，
标准 logging 会忽略这些 kwargs，只打印消息本身——不影响功能。
"""
from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar

from app.core.config import settings

# trace_id 上下文变量，便于跨函数追踪同一请求
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


class _TraceFormatter(logging.Formatter):
    """把当前请求 trace_id 注入日志行。"""

    def format(self, record: logging.LogRecord) -> str:
        record.trace_id = _trace_id_var.get() or "-"
        return super().format(record)


def new_trace_id() -> str:
    trace_id = uuid.uuid4().hex[:12]
    _trace_id_var.set(trace_id)
    return trace_id


def get_trace_id() -> str:
    return _trace_id_var.get()


def clear_trace_id() -> None:
    _trace_id_var.set("")


def setup_logging() -> None:
    """初始化根 logger（单 handler，带 trace_id 字段）。"""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        _TraceFormatter(
            "%(asctime)s %(levelname)s [%(trace_id)s] %(name)s: %(message)s"
        )
    )

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


class _CompatLogger:
    """兼容 structlog 风格的 logger 调用：logger.info("event", key=value)。"""

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    @staticmethod
    def _format_message(msg: str, **kwargs: object) -> str:
        if not kwargs:
            return str(msg)
        extras = ", ".join(f"{key}={value!r}" for key, value in kwargs.items())
        return f"{msg} {extras}"

    def info(self, msg: str, *args: object, **kwargs: object) -> None:
        self._logger.info(self._format_message(msg, **kwargs), *args)

    def warning(self, msg: str, *args: object, **kwargs: object) -> None:
        self._logger.warning(self._format_message(msg, **kwargs), *args)

    def error(self, msg: str, *args: object, **kwargs: object) -> None:
        self._logger.error(self._format_message(msg, **kwargs), *args)

    def exception(self, msg: str, *args: object, **kwargs: object) -> None:
        self._logger.exception(self._format_message(msg, **kwargs), *args)

    def debug(self, msg: str, *args: object, **kwargs: object) -> None:
        self._logger.debug(self._format_message(msg, **kwargs), *args)

    def critical(self, msg: str, *args: object, **kwargs: object) -> None:
        self._logger.critical(self._format_message(msg, **kwargs), *args)

    def __getattr__(self, item: str):
        return getattr(self._logger, item)


def get_logger(name: str | None = None) -> _CompatLogger:
    return _CompatLogger(logging.getLogger(name))

