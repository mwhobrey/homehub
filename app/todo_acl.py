"""Access control for todo lists (Firebase shares + legacy creator)."""

from __future__ import annotations

from flask import has_request_context, session

from .models import TodoList, TodoListShare, db
from .user_context import current_firebase_uid, is_admin, uses_firebase


def _viewer_uid() -> str:
    if uses_firebase():
        return current_firebase_uid()
    return session.get('legacy_user') or session.get('display_name') or ''


def list_owner_key(tl: TodoList) -> str:
    return (tl.owner_uid or tl.creator or '').strip()


def can_view_todo_list(tl: TodoList, viewer_uid: str | None = None) -> bool:
    if not tl or tl.archived:
        return False
    if not uses_firebase():
        vis = (tl.visibility or 'private').lower()
        if vis == 'household':
            return True
        actor = viewer_uid or _viewer_uid()
        if is_admin(actor):
            return True
        owner = list_owner_key(tl)
        if not owner:
            return True
        if not actor:
            return True
        if actor == owner or actor == (tl.creator or ''):
            return True
        return TodoListShare.query.filter_by(
            todo_list_id=tl.id,
            grantee_uid=actor,
        ).first() is not None
    viewer_uid = viewer_uid or _viewer_uid()
    if not viewer_uid:
        return False
    if has_request_context() and is_admin():
        return True
    if (tl.visibility or 'private').lower() == 'household':
        return True
    if tl.owner_uid == viewer_uid:
        return True
    return TodoListShare.query.filter_by(
        todo_list_id=tl.id,
        grantee_uid=viewer_uid,
    ).first() is not None


def can_write_todo_list(tl: TodoList, viewer_uid: str | None = None) -> bool:
    if not can_view_todo_list(tl, viewer_uid):
        return False
    if not uses_firebase():
        actor = viewer_uid or _viewer_uid()
        if is_admin(actor):
            return True
        owner = list_owner_key(tl)
        if not owner or not actor:
            return True
        if actor == owner or actor == (tl.creator or ''):
            return True
        share = TodoListShare.query.filter_by(
            todo_list_id=tl.id,
            grantee_uid=actor,
            can_write=True,
        ).first()
        return share is not None
    viewer_uid = viewer_uid or _viewer_uid()
    if has_request_context() and is_admin():
        return True
    if (tl.visibility or 'private').lower() == 'household':
        return True
    if tl.owner_uid == viewer_uid:
        return True
    share = TodoListShare.query.filter_by(
        todo_list_id=tl.id,
        grantee_uid=viewer_uid,
        can_write=True,
    ).first()
    return share is not None


def visible_todo_list_ids(viewer_uid: str | None = None) -> set[int]:
    ids = set()
    for tl in TodoList.query.filter_by(archived=False).all():
        if can_view_todo_list(tl, viewer_uid):
            ids.add(tl.id)
    return ids


def normalize_todo_list_shares(owner_uid: str, raw_shares, roster_uids: set[str]) -> list[dict]:
    if not isinstance(raw_shares, list):
        return []
    normalized = []
    seen = set()
    for item in raw_shares:
        if not isinstance(item, dict):
            continue
        grantee = (item.get('grantee_uid') or '').strip()
        if not grantee or grantee == owner_uid or grantee not in roster_uids or grantee in seen:
            continue
        seen.add(grantee)
        normalized.append({
            'grantee_uid': grantee,
            'can_write': bool(item.get('can_write')),
        })
    return normalized


def apply_todo_list_shares(tl: TodoList, owner_uid: str, raw_shares, roster_uids: set[str]) -> None:
    shares = normalize_todo_list_shares(owner_uid, raw_shares, roster_uids)
    TodoListShare.query.filter_by(todo_list_id=tl.id).delete()
    for s in shares:
        db.session.add(TodoListShare(
            todo_list_id=tl.id,
            grantee_uid=s['grantee_uid'],
            can_write=s['can_write'],
        ))
