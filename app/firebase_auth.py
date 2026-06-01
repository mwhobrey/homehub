"""Firebase Admin SDK — verify Google sign-in ID tokens."""

from __future__ import annotations

import json
import os

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

_initialized = False


def init_firebase() -> None:
    global _initialized
    if _initialized:
        return
    json_blob = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON', '').strip()
    path = os.environ.get('FIREBASE_SERVICE_ACCOUNT_FILE', '').strip()
    if json_blob:
        cred = credentials.Certificate(json.loads(json_blob))
    elif path and os.path.isfile(path):
        cred = credentials.Certificate(path)
    else:
        hint = f'path={path!r}'
        if path and os.path.isdir(path):
            hint += ' (is a directory — host file was missing when container started; recreate container)'
        elif path:
            hint += ' (file not found inside container)'
        raise RuntimeError(
            'Firebase credentials missing. Set FIREBASE_SERVICE_ACCOUNT_FILE or '
            f'FIREBASE_SERVICE_ACCOUNT_JSON. Checked {hint}'
        )
    firebase_admin.initialize_app(cred)
    _initialized = True


def verify_id_token(id_token: str) -> dict:
    init_firebase()
    return firebase_auth.verify_id_token(id_token, check_revoked=True)
