# 异常与统一响应

> 业务异常统一入口 + 统一响应 Result[T>。

---

## 1. 统一响应

### 1.1 Result 类

```python
# app/core/result.py
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")

class Result(BaseModel, Generic[T]):
    code: int
    message: str
    data: T | None = None
    
    @classmethod
    def ok(cls, data: T | None = None, message: str = "success") -> "Result[T]":
        return cls(code=0, message=message, data=data)
    
    @classmethod
    def error(cls, code: int, message: str, data: T | None = None) -> "Result[T]":
        return cls(code=code, message=message, data=data)
```

### 1.2 响应约定

| 场景 | HTTP | code | message |
|---|---|---|---|
| 成功 | 200 | 0 | "success" |
| 业务异常 | 200 | 业务错误码 | 错误描述 |
| 系统异常 | 500 | -1 | "internal server error" |

**所有接口 HTTP 都是 200**，错误用 `code` 区分（前端统一处理）。

---

## 2. 业务异常

### 2.1 BusinessException

```python
# app/core/exceptions.py
from app.core.result import Result

class BusinessException(Exception):
    def __init__(self, error_code: tuple[int, str], message: str | None = None):
        self.code, default_msg = error_code
        self.message = message or default_msg
        super().__init__(self.message)
    
    def to_result(self) -> Result:
        return Result.error(self.code, self.message)
```

### 2.2 错误码定义

```python
# app/core/error_codes.py
from enum import Enum

class ErrorCode:
    # 通用错误（-1 ~ -99）
    INTERNAL_ERROR = (-1, "internal server error")
    INVALID_PARAMS = (-2, "invalid parameters")
    UNAUTHORIZED = (-3, "unauthorized")
    RATE_LIMITED = (-4, "rate limit exceeded")
    
    # 简历（1000 ~ 1999）
    RESUME_NOT_FOUND = (1001, "简历不存在")
    RESUME_PARSE_FAILED = (1002, "简历解析失败")
    RESUME_DUPLICATE = (1003, "简历已存在")
    RESUME_FILE_TOO_LARGE = (1004, "简历文件过大")
    RESUME_INVALID_TYPE = (1005, "简历文件类型不支持")
    
    # JD（2000 ~ 2999）
    JD_NOT_FOUND = (2001, "JD 不存在")
    JD_CRAWL_FAILED = (2002, "JD 抓取失败")
    JD_EXTRACT_FAILED = (2003, "JD 结构化抽取失败")
    JD_SOURCE_UNSUPPORTED = (2004, "暂不支持该 JD 来源")
    JD_ALREADY_EXISTS = (2005, "JD 已存在")
    
    # 定制化（3000 ~ 3999）
    CUSTOMIZATION_NOT_FOUND = (3001, "定制化任务不存在")
    CUSTOMIZATION_PROCESSING = (3002, "定制化任务正在处理")
    CUSTOMIZATION_FAILED = (3003, "定制化任务失败")
    CUSTOMIZATION_INVALID_INPUT = (3004, "定制化输入不合法")
    
    # LLM（4000 ~ 4999）
    LLM_PROVIDER_DISABLED = (4001, "模型未启用")
    LLM_PROVIDER_NOT_FOUND = (4002, "模型不存在")
    LLM_PROVIDER_TYPE_UNKNOWN = (4003, "未知 Provider 类型")
    LLM_API_KEY_INVALID = (4004, "API Key 无效")
    LLM_RATE_LIMITED = (4005, "模型调用限流")
    LLM_TIMEOUT = (4006, "模型调用超时")
    LLM_OUTPUT_INVALID = (4007, "模型输出格式错误")
    
    # 存储（5000 ~ 5999）
    STORAGE_WRITE_FAILED = (5001, "文件写入失败")
    STORAGE_READ_FAILED = (5002, "文件读取失败")
```

### 2.3 使用

```python
# 抛出业务异常
if not resume:
    raise BusinessException(ErrorCode.RESUME_NOT_FOUND)

# 自定义错误消息
if file_size > MAX_SIZE:
    raise BusinessException(ErrorCode.RESUME_FILE_TOO_LARGE, f"文件 {file_size} 超过 10MB")
```

---

## 3. 全局异常处理

### 3.1 FastAPI 异常处理器

```python
# app/main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.exception_handler(BusinessException)
async def business_exception_handler(request: Request, exc: BusinessException):
    return JSONResponse(
        status_code=200,
        content=Result.error(exc.code, exc.message).model_dump(),
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=200,
        content=Result.error(-1, "internal server error").model_dump(),
    )
```

**注意**：业务异常也返回 HTTP 200，错误用 `code` 字段区分。

---

## 4. 限流

### 4.1 slowapi

```python
# app/core/rate_limit.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

### 4.2 使用

```python
from app.core.rate_limit import limiter

@router.post("/jds/url")
@limiter.limit("2/second")
async def submit_jd_url(request: Request, req: JdUrlRequest):
    ...
```

### 4.3 自定义错误响应

```python
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=200,
        content=Result.error(-4, "rate limit exceeded").model_dump(),
    )
```

---

## 5. 日志规范

### 5.1 结构化日志

```python
# app/core/logging.py
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger()
```

### 5.2 使用

```python
# 业务日志
log.info("resume_uploaded", resume_id=resume.id, file_size=file.size)

# 错误日志（异常必须作为参数）
log.error("resume_parse_failed", resume_id=resume.id, error=str(e), exc_info=e)
```

### 5.3 脱敏

```python
# API Key 脱敏
def mask_api_key(key: str) -> str:
    if not key or len(key) < 8:
        return "***"
    return key[:4] + "***" + key[-4:]

log.info("provider_loaded", name=provider.name, api_key=mask_api_key(api_key))
```

---

## 6. 校验

### 6.1 Pydantic 校验

```python
# app/schemas/jd.py
from pydantic import BaseModel, Field, field_validator

class JdUrlRequest(BaseModel):
    url: str = Field(..., min_length=10, max_length=512)
    
    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL 必须以 http:// 或 https:// 开头")
        return v
```

校验失败 → FastAPI 自动返回 422，需要转成统一响应：

```python
from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in errors)
    return JSONResponse(
        status_code=200,
        content=Result.error(-2, msg).model_dump(),
    )
```

---

## 7. 测试

```python
# tests/unit/test_exceptions.py
def test_business_exception_to_result():
    exc = BusinessException(ErrorCode.RESUME_NOT_FOUND)
    result = exc.to_result()
    assert result.code == 1001
    assert result.message == "简历不存在"

def test_business_exception_custom_message():
    exc = BusinessException(ErrorCode.RESUME_FILE_TOO_LARGE, "文件超过 10MB")
    assert exc.message == "文件超过 10MB"
```

---

## 8. 面试讲点

1. **"为什么所有接口 HTTP 都是 200？"**
   > 业务错误是业务逻辑问题，不是 HTTP 协议错误。前端统一处理 `code` 字段，不需要按 HTTP 状态码分支。

2. **"业务异常和系统异常怎么区分？"**
   > 业务异常用 `BusinessException(ErrorCode, msg)`，自定义错误码。系统异常（DB 挂了、LLM 挂了）走通用 500 处理 + 日志埋点。

3. **"错误码怎么设计？"**
   > 分模块（1000-简历/2000-JD/3000-定制化/4000-LLM），每个模块内递增。负数给通用错误。错误码 + 默认消息，避免每个地方都写错误描述。

4. **"日志怎么脱敏？"**
   > API Key 走加密 + 脱敏函数（只显首尾4 位）。JD 原文超过 200 字符截断。绝对不允许日志中出现明文敏感信息。