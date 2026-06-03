"""Per-user preferences (theme, color mode) stored in app_setting."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from flask import has_app_context

from .security import sanitize_text
from .settings_service import THEME_KEYS, _deep_merge, _get_setting, _set_setting
from .user_context import (
    current_firebase_uid,
    is_logged_in,
    resolve_user,
    resolve_user_from_args,
    uses_firebase,
)

_KEY_PREFIX = 'user_prefs:'
_COLOR_MODES = frozenset({'system', 'light', 'dark'})


def user_storage_key(*, actor: str | None = None) -> str | None:
    """Stable app_setting key suffix for the current or given user."""
    if uses_firebase():
        uid = current_firebase_uid()
        return f'firebase:{uid}' if uid else None
    name = sanitize_text(actor or resolve_user_from_args() or resolve_user() or '')[:120]
    if not name:
        return None
    safe = re.sub(r'[^a-zA-Z0-9._-]+', '_', name)
    return f'legacy:{safe}' if safe else None


def _prefs_db_key(storage_key: str) -> str:
    return f'{_KEY_PREFIX}{storage_key}'


def _load_raw_prefs(storage_key: str) -> dict:
    raw = _get_setting(_prefs_db_key(storage_key))
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def load_user_preferences(*, actor: str | None = None) -> dict:
    key = user_storage_key(actor=actor)
    if not key or not has_app_context():
        return {}
    prefs = _load_raw_prefs(key)
    mode = str(prefs.get('color_mode') or 'system').lower()
    if mode not in _COLOR_MODES:
        mode = 'system'
    theme = prefs.get('theme')
    if not isinstance(theme, dict):
        theme = {}
    return {
        'storage_key': key,
        'color_mode': mode,
        'theme': {k: theme.get(k, '') for k in THEME_KEYS if theme.get(k)},
        'has_overrides': bool(theme) or mode != 'system',
    }


def merge_theme(base_theme: dict, user_theme: dict | None) -> dict:
    if not user_theme:
        return deepcopy(base_theme)
    return _deep_merge(base_theme or {}, user_theme)


def effective_theme_for_request(config: dict) -> dict:
    base = dict(config.get('theme') or {})
    prefs = load_user_preferences()
    return merge_theme(base, prefs.get('theme'))


def color_mode_for_request() -> str:
    return load_user_preferences().get('color_mode', 'system')


def build_user_preferences_form_context(config: dict, *, actor: str | None = None) -> dict:
    prefs = load_user_preferences(actor=actor)
    household = dict(config.get('theme') or {})
    effective = merge_theme(household, prefs.get('theme'))
    return {
        'color_mode': prefs.get('color_mode', 'system'),
        'theme': {k: prefs.get('theme', {}).get(k, '') for k in THEME_KEYS},
        'effective_theme': effective,
        'household_theme': household,
        'has_user_overrides': prefs.get('has_overrides', False),
        'storage_key': prefs.get('storage_key'),
    }


def save_user_preferences_from_form(form, *, base_config: dict | None = None) -> None:
    actor = None if uses_firebase() else sanitize_text(form.get('user', ''))[:120]
    storage_key = user_storage_key(actor=actor or None)
    if not storage_key:
        raise ValueError('User identity required to save preferences')

    mode = sanitize_text(form.get('color_mode', 'system'))[:16].lower()
    if mode not in _COLOR_MODES:
        mode = 'system'

    existing = _load_raw_prefs(storage_key)
    base = base_config or {}
    household = dict((base.get('theme') or {}))
    stored_theme = existing.get('theme') if isinstance(existing.get('theme'), dict) else {}
    theme = _deep_merge(household, stored_theme)

    for key in THEME_KEYS:
        raw = sanitize_text(form.get(f'theme_{key}', ''))[:32]
        if not raw:
            continue
        if not raw.startswith('#'):
            raw = f'#{raw.lstrip("#")}'
        theme[key] = raw

    # Persist only deltas from household defaults
    user_theme: dict[str, str] = {}
    for key in THEME_KEYS:
        val = theme.get(key)
        if val and val != household.get(key):
            user_theme[key] = val

    payload = {'color_mode': mode, 'theme': user_theme}
    _set_setting(_prefs_db_key(storage_key), json.dumps(payload))


def clear_user_preferences(*, actor: str | None = None) -> None:
    from .models import db

    storage_key = user_storage_key(actor=actor)
    if not storage_key:
        raise ValueError('User identity required')
    db.session.execute(
        db.text('DELETE FROM app_setting WHERE key=:k'),
        {'k': _prefs_db_key(storage_key)},
    )
    db.session.commit()


def migrate_legacy_system_theme_to_user(storage_key: str) -> bool:
    """One-time: move old global settings:theme into the saving user's prefs if empty."""
    legacy = _get_setting('settings:theme')
    if not legacy:
        return False
    prefs = _load_raw_prefs(storage_key)
    if prefs.get('theme'):
        return False
    try:
        theme = json.loads(legacy)
    except (TypeError, ValueError):
        return False
    if not isinstance(theme, dict):
        return False
    payload = {
        'color_mode': prefs.get('color_mode') or 'system',
        'theme': {k: theme[k] for k in THEME_KEYS if k in theme},
    }
    _set_setting(_prefs_db_key(storage_key), json.dumps(payload))
    return True
