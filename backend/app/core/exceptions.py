"""业务错误码 + 统一异常。

设计文档 §9.1：所有业务异常都通过 BusinessException 抛出，
由全局异常处理器统一转成 Result.fail。
"""
from __future__ import annotations

from enum import IntEnum


class ErrorCode(IntEnum):
    """错误码：分模块递增（与 docs/architecture/error-handling.md §2.2 对齐）。"""

    # 通用 0 ~ -99
    SUCCESS = 0
    INTERNAL_ERROR = -1
    INVALID_PARAMS = -2
    UNAUTHORIZED = -3
    RATE_LIMITED = -4

    # 简历 1001 ~ 1099
    RESUME_NOT_FOUND = 1001
    RESUME_PARSE_FAILED = 1002
    RESUME_DUPLICATE = 1003
    RESUME_FILE_TOO_LARGE = 1004
    RESUME_INVALID_TYPE = 1005
    RESUME_UNSUPPORTED_FORMAT = 110004  # 与 design.md ErrorCode 表保持兼容

    # JD 2001 ~ 2099
    JD_NOT_FOUND = 2001
    JD_CRAWL_FAILED = 2002
    JD_EXTRACT_FAILED = 2003
    JD_SOURCE_UNSUPPORTED = 2004
    JD_ALREADY_EXISTS = 2005

    # 定制化 3001 ~ 3099
    CUSTOMIZATION_NOT_FOUND = 3001
    CUSTOMIZATION_PROCESSING = 3002
    CUSTOMIZATION_FAILED = 3003
    CUSTOMIZATION_INVALID_INPUT = 3004

    # LLM 4001 ~ 4099
    LLM_PROVIDER_DISABLED = 4001
    LLM_PROVIDER_NOT_FOUND = 4002
    LLM_PROVIDER_TYPE_UNKNOWN = 4003
    LLM_API_KEY_INVALID = 4004
    LLM_RATE_LIMITED = 4005
    LLM_TIMEOUT = 4006
    LLM_OUTPUT_INVALID = 4007
    LLM_NO_PROVIDER_AVAILABLE = 4008

    # 存储 5001 ~ 5099
    STORAGE_WRITE_FAILED = 5001
    STORAGE_READ_FAILED = 5002

    # design.md ErrorCode 中保留的细粒度码（用于 W2+ 模块）
    UNKNOWN_ERROR = 100000
    INVALID_PARAM = 100001
    NOT_FOUND = 100002
    FORBIDDEN = 100004
    RESUME_PARSE_FAILED_OLD = 110002
    JD_PARSE_FAILED = 120002
    UNSUPPORTED_JD_SOURCE = 120003
    JD_CRAWL_FAILED_OLD = 120004
    CUSTOMIZATION_FAILED_OLD = 130002
    CUSTOMIZATION_INVALID_INPUT_OLD = 130003
    RETRIEVAL_FAILED = 140001
    EMBEDDING_FAILED = 140002
    LLM_INVOKE_FAILED = 150003
    LLM_STRUCTURED_OUTPUT_FAILED = 150004
    EVALUATION_FAILED = 160001
    CRAWLER_TIMEOUT = 170001
    CRAWLER_BLOCKED = 170002
    CRAWLER_UA_EXHAUSTED = 170003


class BusinessException(Exception):
    """业务异常基类。"""

    def __init__(
        self,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        message: str = "",
        *,
        data: dict | None = None,
    ) -> None:
        self.code = code
        self.message = message or _default_message(code)
        self.data = data or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"[{int(self.code)}] {self.message}"


def _default_message(code: ErrorCode) -> str:
    table: dict[int, str] = {
        int(ErrorCode.SUCCESS): "ok",
        int(ErrorCode.INTERNAL_ERROR): "internal server error",
        int(ErrorCode.INVALID_PARAMS): "invalid parameters",
        int(ErrorCode.UNAUTHORIZED): "unauthorized",
        int(ErrorCode.RATE_LIMITED): "rate limit exceeded",
        int(ErrorCode.RESUME_NOT_FOUND): "简历不存在",
        int(ErrorCode.RESUME_PARSE_FAILED): "简历解析失败",
        int(ErrorCode.RESUME_PARSE_FAILED_OLD): "简历解析失败",
        int(ErrorCode.RESUME_DUPLICATE): "简历已存在",
        int(ErrorCode.RESUME_FILE_TOO_LARGE): "简历文件过大",
        int(ErrorCode.RESUME_INVALID_TYPE): "简历文件类型不支持",
        int(ErrorCode.RESUME_UNSUPPORTED_FORMAT): "简历格式不支持",
        int(ErrorCode.JD_NOT_FOUND): "JD 不存在",
        int(ErrorCode.JD_CRAWL_FAILED): "JD 抓取失败",
        int(ErrorCode.JD_CRAWL_FAILED_OLD): "JD 抓取失败",
        int(ErrorCode.JD_EXTRACT_FAILED): "JD 结构化抽取失败",
        int(ErrorCode.JD_PARSE_FAILED): "JD 解析失败",
        int(ErrorCode.JD_SOURCE_UNSUPPORTED): "暂不支持该 JD 来源",
        int(ErrorCode.UNSUPPORTED_JD_SOURCE): "暂不支持该 JD 来源",
        int(ErrorCode.JD_ALREADY_EXISTS): "JD 已存在",
        int(ErrorCode.CUSTOMIZATION_NOT_FOUND): "定制化任务不存在",
        int(ErrorCode.CUSTOMIZATION_PROCESSING): "定制化任务正在处理",
        int(ErrorCode.CUSTOMIZATION_FAILED): "定制化任务失败",
        int(ErrorCode.CUSTOMIZATION_FAILED_OLD): "定制化执行失败",
        int(ErrorCode.CUSTOMIZATION_INVALID_INPUT): "定制化输入不合法",
        int(ErrorCode.CUSTOMIZATION_INVALID_INPUT_OLD): "定制化输入不合法",
        int(ErrorCode.LLM_PROVIDER_DISABLED): "模型未启用",
        int(ErrorCode.LLM_PROVIDER_NOT_FOUND): "模型不存在",
        int(ErrorCode.LLM_PROVIDER_TYPE_UNKNOWN): "未知 Provider 类型",
        int(ErrorCode.LLM_API_KEY_INVALID): "API Key 无效",
        int(ErrorCode.LLM_RATE_LIMITED): "模型调用限流",
        int(ErrorCode.LLM_TIMEOUT): "模型调用超时",
        int(ErrorCode.LLM_OUTPUT_INVALID): "模型输出格式错误",
        int(ErrorCode.LLM_NO_PROVIDER_AVAILABLE): "无可用的 LLM 提供方",
        int(ErrorCode.LLM_INVOKE_FAILED): "LLM 调用失败",
        int(ErrorCode.LLM_STRUCTURED_OUTPUT_FAILED): "LLM 结构化输出失败",
        int(ErrorCode.STORAGE_WRITE_FAILED): "文件写入失败",
        int(ErrorCode.STORAGE_READ_FAILED): "文件读取失败",
        int(ErrorCode.RETRIEVAL_FAILED): "召回失败",
        int(ErrorCode.EMBEDDING_FAILED): "向量化失败",
        int(ErrorCode.EVALUATION_FAILED): "评估失败",
        int(ErrorCode.CRAWLER_TIMEOUT): "爬虫超时",
        int(ErrorCode.CRAWLER_BLOCKED): "被目标站点拒绝",
        int(ErrorCode.CRAWLER_UA_EXHAUSTED): "UA 池耗尽",
        int(ErrorCode.UNKNOWN_ERROR): "未知错误",
        int(ErrorCode.INVALID_PARAM): "参数非法",
        int(ErrorCode.NOT_FOUND): "资源不存在",
        int(ErrorCode.FORBIDDEN): "禁止访问",
    }
    return table.get(int(code), "unknown error")
