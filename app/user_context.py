"""Server-side user identity and authorization (Firebase or legacy)."""

from __future__ import annotations

from flask import current_app, request, session

from .security import sanitize_text


def auth_mode() -> str:
    return (current_app.config.get('HOMEHUB_CONFIG', {}).get('auth') or {}).get('mode', 'legacy')


def uses_firebase() -> bool:
    return auth_mode() == 'firebase'


def password_required() -> bool:
    cfg = current_app.config.get('HOMEHUB_CONFIG', {})
    return bool(cfg.get('password_hash'))


def is_logged_in() -> bool:
    if uses_firebase():
        return bool(session.get('firebase_uid'))
    if password_required():
        return bool(session.get('authed'))
    return True


def current_email() -> str:
    return (session.get('firebase_email') or '').lower()


def current_display_name() -> str:
    if uses_firebase():
        return session.get('display_name') or session.get('firebase_email') or ''
    return ''


def is_admin(actor: str | None = None) -> bool:
    cfg = current_app.config.get('HOMEHUB_CONFIG', {})
    auth = cfg.get('auth') or {}
    if uses_firebase():
        admins = {e.lower() for e in auth.get('admin_emails', []) if e}
        return current_email() in admins
    user = actor or current_display_name() or resolve_user()
    return is_admin_for(user)


def is_admin_for(actor: str) -> bool:
    """Legacy-compatible admin check using a display name."""
    if uses_firebase():
        return is_admin()
    cfg = current_app.config.get('HOMEHUB_CONFIG', {})
    admin_name = cfg.get('admin_name', 'Administrator')
    admin_aliases = {admin_name, 'Administrator', 'admin'}
    return actor in admin_aliases


def can_modify_record(record_creator: str | None, actor: str | None = None) -> bool:
    if uses_firebase():
        if is_admin():
            return True
        name = current_display_name()
        return bool(name) and name == (record_creator or '')
    user = actor or ''
    # Legacy LAN: empty client identity falls back to open edit among authed users
    if not user:
        return True
    if is_admin_for(user):
        return True
    return user == (record_creator or '')


def resolve_actor(*, form_key: str = 'creator', json_payload: dict | None = None, json_key: str = 'creator') -> str:
    """Identity for writes and permission checks — never trust client in Firebase mode."""
    if uses_firebase():
        return current_display_name()
    if json_payload is not None:
        return sanitize_text(json_payload.get(json_key, ''))
    return sanitize_text(request.form.get(form_key, ''))


def resolve_user(*, form_key: str = 'user', json_payload: dict | None = None, json_key: str = 'creator') -> str:
    if uses_firebase():
        return current_display_name()
    if json_payload is not None:
        return sanitize_text(json_payload.get(json_key, ''))
    return sanitize_text(request.form.get(form_key, ''))


def resolve_user_from_args() -> str:
    if uses_firebase():
        return current_display_name()
    return sanitize_text(request.args.get('user') or request.args.get('creator') or '')
