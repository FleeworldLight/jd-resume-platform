"""测试：API Key Fernet 加密 / 解密。"""
from __future__ import annotations

from app.core.security import decrypt_api_key, encrypt_api_key


def test_encrypt_decrypt_roundtrip() -> None:
    plain = "sk-test-1234567890abcdef"
    cipher = encrypt_api_key(plain)
    assert cipher != plain
    assert decrypt_api_key(cipher) == plain


def test_encrypt_empty() -> None:
    assert encrypt_api_key("") == ""
    assert decrypt_api_key("") == ""


def test_decrypt_invalid_raises() -> None:
    from app.core.exceptions import BusinessException

    try:
        decrypt_api_key("not-a-valid-fernet-token")
    except BusinessException as exc:
        assert "解密失败" in exc.message
    else:
        raise AssertionError("应该抛 BusinessException")
