"""测试：Pydantic Schema 校验。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.jd import JdTextRequest, JdUrlRequest


class TestJdTextRequest:
    def test_valid(self) -> None:
        req = JdTextRequest(text="x" * 100)
        assert len(req.text) == 100

    def test_too_short(self) -> None:
        with pytest.raises(ValidationError):
            JdTextRequest(text="abc")

    def test_too_long(self) -> None:
        with pytest.raises(ValidationError):
            JdTextRequest(text="x" * 30_000)


class TestJdUrlRequest:
    def test_valid_https(self) -> None:
        req = JdUrlRequest(url="https://www.nowcoder.com/jobs/123")
        assert req.url.startswith("https://")

    def test_valid_http(self) -> None:
        req = JdUrlRequest(url="http://www.zhipin.com/position/1")
        assert req.url.startswith("http://")

    def test_invalid_scheme(self) -> None:
        with pytest.raises(ValidationError):
            JdUrlRequest(url="ftp://example.com")

    def test_too_short(self) -> None:
        with pytest.raises(ValidationError):
            JdUrlRequest(url="http://a")
