"""统一响应包装：Result[T]。

设计文档 §9.1：所有接口 HTTP 200，通过 code 区分成功失败。
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from app.core.exceptions import ErrorCode

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    """统一响应结构。"""

    code: int = Field(default=ErrorCode.SUCCESS, description="错误码，0=成功")
    message: str = Field(default="ok", description="人类可读消息")
    data: T | None = Field(default=None, description="业务数据")

    @classmethod
    def ok(cls, data: T | None = None, message: str = "ok") -> "Result[T]":
        return cls(code=ErrorCode.SUCCESS, message=message, data=data)

    @classmethod
    def fail(
        cls,
        code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        message: str = "",
        data: Any = None,
    ) -> "Result":
        return cls(code=code, message=message, data=data)
