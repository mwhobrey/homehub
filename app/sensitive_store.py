"""Encrypt sensitive values at rest (QR payloads) using the app SECRET_KEY."""

from __future__ import annotations

import base64
import hashlib

from flask import current_app

_PREFIX = 'enc:v1:'


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
    return _fernet().decrypt(token.encode('ascii')).decode('utf-8')
