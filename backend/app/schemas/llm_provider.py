"""LLM Provider Schemas。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LlmProviderBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    provider_type: str = Field(..., min_length=1, max_length=32)
    base_url: str | None = Field(default=None, max_length=512)
    chat_model: str | None = Field(default=None, max_length=128)
    embedding_model: str | None = Field(default=None, max_length=128)
    is_default: bool = False
    enabled: bool = True


class LlmProviderCreate(LlmProviderBase):
    api_key: str | None = Field(default=None, description="明文 API Key，服务端 Fernet 加密入库")


class LlmProviderUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    base_url: str | None = Field(default=None, max_length=512)
    chat_model: str | None = Field(default=None, max_length=128)
    embedding_model: str | None = Field(default=None, max_length=128)
    api_key: str | None = None
    is_default: bool | None = None
    enabled: bool | None = None


class LlmProviderResponse(BaseModel):
    """响应：不返回明文 API Key，只回显是否配置。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    provider_type: str
    base_url: str | None = None
    chat_model: str | None = None
    embedding_model: str | None = None
    is_default: bool
    enabled: bool
    has_api_key: bool = False
    api_key_masked: str | None = None
    created_at: datetime
    updated_at: datetime
