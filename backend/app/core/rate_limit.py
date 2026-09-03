"""限流：基于 slowapi。

设计文档 §9.2：爬虫 2 QPS，LLM 5 QPS。
error-handling.md §4：限流统一通过 Limiter + 自定义异常处理器返回。
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
