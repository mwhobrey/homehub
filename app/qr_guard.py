"""QR / WiFi history hardening helpers."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta

from flask import current_app

from .sensitive_store import decrypt_sensitive, encrypt_sensitive

_WIFI_PAYLOAD_RE = re.compile(r'^WIFI:', re.I)
_WIFI_PASS_RE = re.compile(r'P:([^;]*)', re.I)
_WIFI_SSID_RE = re.compile(r'S:([^;]*)', re.I)


def wifi_to_qrtext(raw: str) -> str | None:
    """Parse wifi shorthand: ssid:name pass:secret type:wpa hidden:false"""
    if not raw:
        return None
    s = raw.strip()
    if 'ssid:' not in s or 'pass:' not in s:
        return None
    parts = {}
    for token in s.split():
        if ':' in token:
            k, v = token.split(':', 1)
            parts[k.strip().lower()] = v.strip()
    if 'ssid' not in parts or 'pass' not in parts:
        return None
    enc = (parts.get('type') or 'wpa').upper()
    if enc not in ('WPA', 'WEP', 'NOPASS'):
        enc = 'WPA'
    hidden = (parts.get('hidden') or 'false').lower() in ('1', 'true', 'yes')

    def esc(x: str) -> str:
        return (x or '').replace('\\', r'\\').replace(';', r'\;').replace(',', r'\,').replace('\\\\', '\\')

    ssid = esc(parts['ssid'])
    pwd = esc(parts['pass'])
    return f"WIFI:T:{enc};S:{ssid};P:{pwd};H:{'true' if hidden else 'false'};;"


def qr_settings() -> dict:
    cfg = current_app.config.get('HOMEHUB_CONFIG', {})
    hard = cfg.get('hardening') or {}
    qr = hard.get('qr_generator') or {}
    return {
        'max_payload_length': int(qr.get('max_payload_length', 2048)),
        'store_wifi_history': bool(qr.get('store_wifi_history', False)),
        'history_retention_days': int(qr.get('history_retention_days', 7)),
        'encrypt_payloads': bool(qr.get('encrypt_payloads', True)),
        'admin_only_wifi': bool(qr.get('admin_only_wifi', False)),
        'qr_dir_name': 'qr',
    }


def qr_storage_dir() -> str:
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    path = os.path.join(base, 'data', qr_settings()['qr_dir_name'])
    os.makedirs(path, exist_ok=True)
    return path


def is_wifi_payload(payload: str) -> bool:
    return bool(payload and _WIFI_PAYLOAD_RE.match(payload.strip()))


def wifi_ssid_from_payload(payload: str) -> str:
    m = _WIFI_SSID_RE.search(payload or '')
    return (m.group(1) if m else '').replace('\\;', ';').replace('\\,', ',').replace('\\\\', '\\')


def mask_wifi_payload(payload: str) -> str:
    if not payload:
        return payload
    return _WIFI_PASS_RE.sub('P:***', payload)


def mask_wifi_shorthand(raw: str) -> str:
    """Mask pass: in user shorthand before persistence."""
    if not raw or 'pass:' not in raw.lower():
        return raw
    out = []
    for token in raw.split():
        if ':' in token:
            k, v = token.split(':', 1)
            if k.strip().lower() == 'pass':
                out.append(f'{k}:***')
                continue
        out.append(token)
    return ' '.join(out)


def display_label_for(payload: str, original_input: str | None, is_wifi: bool) -> str:
    if is_wifi:
        ssid = wifi_ssid_from_payload(payload) or 'network'
        return f'WiFi: {ssid}'
    label = (original_input or payload or '').strip()
    if len(label) > 120:
        return label[:117] + '...'
    return label


def prepare_qr_storage(payload: str, original_input: str, is_wifi: bool) -> tuple[str, str, str]:
    """Returns (stored_text, display_label, safe_original_input)."""
    settings = qr_settings()
    safe_original = mask_wifi_shorthand(original_input) if is_wifi else original_input
    display = display_label_for(payload, safe_original, is_wifi)

    if is_wifi and not settings['store_wifi_history']:
        return '', display, safe_original

    stored = payload
    if settings['encrypt_payloads']:
        stored = encrypt_sensitive(payload)
    return stored, display, safe_original


def payload_for_use(record) -> str:
    raw = record.text or ''
    if not raw:
        return ''
    try:
        return decrypt_sensitive(raw)
    except Exception:
        return raw


def purge_expired_qr_history() -> int:
    from .models import QRCode, db

    days = qr_settings()['history_retention_days']
    if days <= 0:
        return 0
    cutoff = datetime.utcnow() - timedelta(days=days)
    stale = QRCode.query.filter(QRCode.timestamp < cutoff).all()
    removed = 0
    base = qr_storage_dir()
    for rec in stale:
        try:
            path = os.path.join(base, rec.filename)
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass
        db.session.delete(rec)
        removed += 1
    if removed:
        db.session.commit()
    return removed


def safe_qr_filename(record_id: int) -> str:
    return f'qr_{record_id}.png'
