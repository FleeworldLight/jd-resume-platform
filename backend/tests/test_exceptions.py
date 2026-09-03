"""测试：异常 → Result 转换。"""
from __future__ import annotations

from app.core.exceptions import BusinessException, ErrorCode
from app.core.result import Result


def test_business_exception_default_message() -> None:
    exc = BusinessException(ErrorCode.RESUME_NOT_FOUND)
    assert int(exc.code) == 1001
    assert "简历不存在" in exc.message


def test_business_exception_custom_message() -> None:
    exc = BusinessException(ErrorCode.RESUME_FILE_TOO_LARGE, "文件 12MB 超限")
    assert "12MB" in exc.message


def test_result_ok() -> None:
    r = Result.ok({"foo": 1})
    assert r.code == 0
    assert r.message == "ok"
    assert r.data == {"foo": 1}


def test_result_fail() -> None:
    r: Result = Result.fail(code=ErrorCode.JD_NOT_FOUND, message="缺")
    assert int(r.code) == 2001
    assert r.message == "缺"


def test_business_exception_to_result() -> None:
    exc = BusinessException(ErrorCode.RESUME_DUPLICATE, "已存在", data={"id": 5})
    r = Result.fail(code=exc.code, message=exc.message, data=exc.data)
    assert int(r.code) == 1003
    assert r.data == {"id": 5}
