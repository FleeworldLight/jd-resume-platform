"""安全工具：API Key Fernet 加密。"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.exceptions import BusinessException, ErrorCode


def _derive_fernet_key() -> bytes:
    """从 secret_key 派生 32 字节 URL-safe base64 key。"""
    raw = settings.fernet_key or settings.secret_key
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    return Fernet(_derive_fernet_key())


def encrypt_api_key(plain: str) -> str:
    if not plain:
        return ""
    return _get_fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_api_key(cipher: str) -> str:
    if not cipher:
        return ""
    try:
        return _get_fernet().decrypt(cipher.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise BusinessException(
            ErrorCode.LLM_PROVIDER_NOT_FOUND, "API Key 解密失败"
        ) from exc
