"""全局配置：环境变量、密钥、路径等。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，从 .env 读取。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用
    app_name: str = "jd-resume-platform"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    # 演示模式：公开部署时设为 true
    # 非 GET 请求只放行「纯计算」类操作（粘贴 JD 结构化、发起定制化、重新解析），
    # 其余写操作（上传文件、删除、抓取、改 Provider）一律 403，详见 main.py
    demo_mode: bool = False

    # 数据库（默认 SQLite：本地双击 start.bat 即可，无需外部服务）
    database_url: str = "sqlite+aiosqlite:///./data/jd_platform.db"
    database_sync_url: str = "sqlite:///./data/jd_platform.db"

    # 安全
    secret_key: str = "change-me-in-production-32bytes-minimum"
    fernet_key: str = ""  # API Key 加密用，留空时用 secret_key 派生

    # 文件存储
    resume_storage_dir: Path = Path("./data/resumes")

    # 爬虫（本地默认启用；需要 pip 装 playwright + 浏览器）
    crawler_enabled: bool = True
    crawler_timeout_sec: int = 30
    crawler_user_agent_pool_size: int = 50

    # LLM
    llm_default_provider: str = "mock"  # mock / openai / anthropic
    embedding_dim: int = 1024  # 与 FakeEmbeddings 维度一致

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
