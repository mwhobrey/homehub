"""Encrypt sensitive values at rest (QR payloads) using the app SECRET_KEY."""

from __future__ import annotations

import base64
import hashlib

from flask import current_app

_PREFIX = 'enc:v1:'


class SensitiveDecryptError(ValueError):
    """Raised when Fernet cannot decrypt (usually SECRET_KEY rotation or dev key churn)."""


def _fernet():
    from cryptography.fernet import Fernet

    secret = (current_app.config.get('SECRET_KEY') or 'dev').encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt_sensitive(value: str) -> str:
    if not value:
        return value
    token = _fernet().encrypt(value.encode('utf-8')).decode('ascii')
    return _PREFIX + token


def decrypt_sensitive(value: str) -> str:
    if not value:
        return value
    if not value.startswith(_PREFIX):
        return value
    token = value[len(_PREFIX) :]
    try:
        return _fernet().decrypt(token.encode('ascii')).decode('utf-8')
    except Exception as exc:
        from cryptography.fernet import InvalidToken

        if isinstance(exc, InvalidToken):
            raise SensitiveDecryptError(
                'Cannot decrypt stored secret — SECRET_KEY likely changed since data was saved. '
                'Set a stable SECRET_KEY (see .env.example) or reconnect Google Calendar.'
            ) from exc
        raise
