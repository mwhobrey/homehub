"""Household reminder/event category definitions (label + color)."""

from __future__ import annotations

import json
import re

from flask import current_app

from .models import db
from .security import normalize_hex_color, sanitize_text

APP_SETTING_KEY = 'reminder_categories'
DEFAULT_COLOR = '#2563eb'
KEY_RE = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')


def _ensure_app_setting_table() -> None:
    db.session.execute(db.text('CREATE TABLE IF NOT EXISTS app_setting (key TEXT PRIMARY KEY, value TEXT)'))


def categories_from_config(config: dict | None = None) -> list[dict]:
    config = config or (current_app.config.get('HOMEHUB_CONFIG') or {})
    rem = config.get('reminders') or {}
    out: list[dict] = []
    for entry in rem.get('categories') or []:
        if not isinstance(entry, dict):
            continue
        key = (entry.get('key') or '').strip().lower()
        if not key or not KEY_RE.match(key):
            continue
        color = normalize_hex_color(entry.get('color')) or DEFAULT_COLOR
        label = sanitize_text(entry.get('label') or key) or key
        out.append({'key': key, 'label': label, 'color': color})
    return out


def slugify_category_key(label: str) -> str:
    raw = sanitize_text(label).lower()
    slug = re.sub(r'[^a-z0-9]+', '_', raw).strip('_')
    if not slug:
        slug = 'category'
    if not slug[0].isalpha():
        slug = f'cat_{slug}'
    return slug[:64]


def normalize_category_list(categories: list) -> list[dict]:
    if not isinstance(categories, list):
        raise ValueError('categories must be a list')
    if len(categories) > 64:
        raise ValueError('Too many categories (max 64)')
    seen: set[str] = set()
    out: list[dict] = []
    for entry in categories:
        if not isinstance(entry, dict):
            raise ValueError('Each category must be an object')
        key = (entry.get('key') or '').strip().lower()
        label = sanitize_text(entry.get('label') or '')
        if not label:
            raise ValueError('Category label is required')
        if not key:
            key = slugify_category_key(label)
        if not KEY_RE.match(key):
            raise ValueError(f'Invalid category key: {key}')
        if key in seen:
            raise ValueError(f'Duplicate category key: {key}')
        seen.add(key)
        color = normalize_hex_color(entry.get('color')) or DEFAULT_COLOR
        out.append({'key': key, 'label': label, 'color': color})
    return out


def merge_import_categories(category_mappings: list[dict]) -> list[dict]:
    """Ensure mapped Google categories exist as local HomeHub reminder categories."""
    existing = {c['key']: dict(c) for c in load_reminder_categories(seed_if_empty=True)}
    changed = False
    for row in category_mappings:
        if not isinstance(row, dict):
            continue
        label = sanitize_text(row.get('target_label') or row.get('source_label') or '').strip()
        if not label:
            continue
        key = (row.get('target_key') or '').strip().lower()
        if not key or not KEY_RE.match(key):
            key = slugify_category_key(label)
        color = normalize_hex_color(row.get('target_color')) or DEFAULT_COLOR
        prev = existing.get(key)
        if not prev:
            existing[key] = {'key': key, 'label': label, 'color': color}
            changed = True
            continue
        if prev.get('label') != label or prev.get('color') != color:
            existing[key] = {'key': key, 'label': label, 'color': color}
            changed = True
    merged = sorted(existing.values(), key=lambda c: (c.get('label') or c.get('key') or '').lower())
    if changed:
        save_reminder_categories(merged)
    return merged


def _load_stored_categories() -> list[dict] | None:
    try:
        _ensure_app_setting_table()
        row = db.session.execute(
            db.text('SELECT value FROM app_setting WHERE key=:k'),
            {'k': APP_SETTING_KEY},
        ).fetchone()
        if not row or not row[0]:
            return None
        data = json.loads(row[0])
        if not isinstance(data, list):
            return None
        return normalize_category_list(data)
    except ValueError:
        raise
    except Exception:
        return None


def load_reminder_categories(config: dict | None = None, *, seed_if_empty: bool = True) -> list[dict]:
    """Merged household categories: DB overrides config defaults when present."""
    try:
        stored = _load_stored_categories()
    except ValueError:
        stored = None
    if stored is not None:
        return stored
    defaults = categories_from_config(config)
    if seed_if_empty and defaults:
        save_reminder_categories(defaults)
        return defaults
    return defaults


def save_reminder_categories(categories: list[dict]) -> list[dict]:
    normalized = normalize_category_list(categories)
    _ensure_app_setting_table()
    db.session.execute(
        db.text(
            'INSERT INTO app_setting(key,value) VALUES(:k, :v) '
            'ON CONFLICT(key) DO UPDATE SET value=excluded.value'
        ),
        {'k': APP_SETTING_KEY, 'v': json.dumps(normalized)},
    )
    db.session.commit()
    return normalized
