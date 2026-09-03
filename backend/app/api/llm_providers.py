"""LLM Provider API。

设计文档 §7：CRUD + 设默认 + test_connection。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.result import Result
from app.schemas.llm_provider import (
    LlmProviderCreate,
    LlmProviderResponse,
    LlmProviderUpdate,
)
from app.services.llm_provider_service import LlmProviderService

router = APIRouter(prefix="/api/llm-providers", tags=["llm-providers"])


def _service(db: AsyncSession = Depends(get_db)) -> LlmProviderService:
    return LlmProviderService(db)


@router.get("", response_model=Result[list[LlmProviderResponse]])
async def list_providers(
    service: LlmProviderService = Depends(_service),
) -> Result[list[LlmProviderResponse]]:
    items = await service.list_all()
    return Result.ok([LlmProviderResponse(**service.to_response(p)) for p in items])


@router.post("", response_model=Result[LlmProviderResponse])
async def create_provider(
    body: LlmProviderCreate,
    service: LlmProviderService = Depends(_service),
) -> Result[LlmProviderResponse]:
    p = await service.create(
        name=body.name,
        provider_type=body.provider_type,
        api_key=body.api_key,
        base_url=body.base_url,
        chat_model=body.chat_model,
        embedding_model=body.embedding_model,
        is_default=body.is_default,
        enabled=body.enabled,
    )
    return Result.ok(LlmProviderResponse(**service.to_response(p)))


@router.put("/{provider_id}", response_model=Result[LlmProviderResponse])
async def update_provider(
    provider_id: int,
    body: LlmProviderUpdate,
    service: LlmProviderService = Depends(_service),
) -> Result[LlmProviderResponse]:
    p = await service.update(
        provider_id,
        name=body.name,
        base_url=body.base_url,
        chat_model=body.chat_model,
        embedding_model=body.embedding_model,
        api_key=body.api_key,
        is_default=body.is_default,
        enabled=body.enabled,
    )
    return Result.ok(LlmProviderResponse(**service.to_response(p)))


@router.delete("/{provider_id}", response_model=Result[None])
async def delete_provider(
    provider_id: int,
    service: LlmProviderService = Depends(_service),
) -> Result[None]:
    await service.delete(provider_id)
    return Result.ok(message="删除成功")


@router.post("/{provider_id}/set-default", response_model=Result[LlmProviderResponse])
async def set_default_provider(
    provider_id: int,
    service: LlmProviderService = Depends(_service),
) -> Result[LlmProviderResponse]:
    p = await service.set_default(provider_id)
    return Result.ok(LlmProviderResponse(**service.to_response(p)))


@router.post("/{provider_id}/test", response_model=Result[dict])
async def test_provider(
    provider_id: int,
    service: LlmProviderService = Depends(_service),
) -> Result[dict]:
    result = await service.test_connection(provider_id)
    return Result.ok(result)
