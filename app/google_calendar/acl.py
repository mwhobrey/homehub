"""Calendar visibility and write-access checks."""

from __future__ import annotations

from flask import current_app, has_request_context

from ..models import (
    CalendarConnection,
    CalendarDisplayPref,
    CalendarShare,
    LinkedCalendar,
    PersonalCalendar,
    PersonalCalendarShare,
    Reminder,
    db,
)
from ..user_context import current_email, is_admin, uses_firebase


def google_calendar_enabled() -> bool:
    cfg = (current_app.config.get('HOMEHUB_CONFIG') or {}).get('google_calendar') or {}
    return bool(cfg.get('enabled')) and uses_firebase()


def _household_uids() -> set[str]:
    """Firebase UIDs we know about — keyed by email from active connections."""
    uids = set()
    for conn in CalendarConnection.query.all():
        if conn.firebase_uid:
            uids.add(conn.firebase_uid)
    return uids


def _viewer_uid() -> str | None:
    from flask import session
    return session.get('firebase_uid')


def can_view_linked_calendar(lc: LinkedCalendar, viewer_uid: str | None = None) -> bool:
    viewer_uid = viewer_uid or _viewer_uid()
    if not viewer_uid:
        return False
    conn = lc.connection or CalendarConnection.query.get(lc.connection_id)
    if not conn:
        return False
    if conn.firebase_uid == viewer_uid:
        return True
    if has_request_context() and is_admin():
        return True
    vis = (lc.visibility or 'household').lower()
    if vis == 'private':
        return False
    if vis == 'household':
        return True
    if vis == 'custom':
        return CalendarShare.query.filter_by(
            linked_calendar_id=lc.id, grantee_uid=viewer_uid
        ).first() is not None
    return False


def is_calendar_visible_to_viewer(lc: LinkedCalendar, viewer_uid: str | None = None) -> bool:
    if not can_view_linked_calendar(lc, viewer_uid):
        return False
    viewer_uid = viewer_uid or _viewer_uid()
    if not viewer_uid:
        return False
    pref = CalendarDisplayPref.query.filter_by(
        viewer_uid=viewer_uid, linked_calendar_id=lc.id
    ).first()
    if pref is not None:
        return bool(pref.visible)
    return True


def visible_linked_calendar_ids(viewer_uid: str | None = None) -> list[int]:
    viewer_uid = viewer_uid or _viewer_uid()
    if not viewer_uid:
        return []
    ids = []
    for lc in LinkedCalendar.query.filter_by(sync_enabled=True).all():
        if is_calendar_visible_to_viewer(lc, viewer_uid):
            ids.append(lc.id)
    return ids


def owns_linked_calendar(lc: LinkedCalendar, uid: str | None = None) -> bool:
    uid = uid or _viewer_uid()
    if not uid or not lc:
        return False
    conn = lc.connection or CalendarConnection.query.get(lc.connection_id)
    return bool(conn and conn.firebase_uid == uid)


def can_write_linked_calendar(lc: LinkedCalendar, viewer_uid: str | None = None) -> bool:
    viewer_uid = viewer_uid or _viewer_uid()
    if not viewer_uid or not lc:
        return False
    if owns_linked_calendar(lc, viewer_uid):
        return True
    share = CalendarShare.query.filter_by(
        linked_calendar_id=lc.id, grantee_uid=viewer_uid, can_write=True
    ).first()
    return share is not None


def can_modify_reminder(reminder: Reminder, actor: str | None = None) -> bool:
    from ..user_context import can_modify_record, current_display_name, is_admin

    if has_request_context() and is_admin():
        return True
    viewer_uid = _viewer_uid()
    if reminder.owner_uid and viewer_uid:
        if reminder.owner_uid == viewer_uid:
            return True
        if reminder.linked_calendar_id:
            lc = LinkedCalendar.query.get(reminder.linked_calendar_id)
            if lc and can_write_linked_calendar(lc, viewer_uid):
                return True
        return False
    name = current_display_name()
    return can_modify_record(reminder.creator, actor or name)


def get_connection_for_uid(uid: str | None = None) -> CalendarConnection | None:
    uid = uid or _viewer_uid()
    if not uid:
        return None
    return CalendarConnection.query.filter_by(firebase_uid=uid).first()


def calendar_connection_active(conn: CalendarConnection | None) -> bool:
    """True when OAuth completed and tokens are stored (not merely oauth start)."""
    if not conn:
        return False
    return bool((conn.refresh_token_enc or '').strip() or (conn.access_token_enc or '').strip())


def resolve_writable_calendar(
    linked_calendar_id: int | None,
    uid: str | None = None,
) -> LinkedCalendar | None:
    uid = uid or _viewer_uid()
    conn = get_connection_for_uid(uid)
    if not conn or not calendar_connection_active(conn):
        return None
    if linked_calendar_id:
        lc = LinkedCalendar.query.get(linked_calendar_id)
        if lc and lc.connection_id == conn.id and owns_linked_calendar(lc, uid):
            return lc
        return None
    if conn.default_linked_calendar_id:
        lc = LinkedCalendar.query.get(conn.default_linked_calendar_id)
        if lc and lc.connection_id == conn.id:
            return lc
    lc = LinkedCalendar.query.filter_by(connection_id=conn.id).first()
    return lc


HOUSEHOLD_VISIBILITY = "household"
PRIVATE_VISIBILITY = "private"


def is_household_personal_calendar(pc: PersonalCalendar | None) -> bool:
    if not pc:
        return False
    return (pc.visibility or PRIVATE_VISIBILITY).lower() == HOUSEHOLD_VISIBILITY


def can_view_personal_calendar(pc: PersonalCalendar, viewer_uid: str | None = None) -> bool:
    viewer_uid = viewer_uid or _viewer_uid()
    if not pc or pc.archived:
        return False
    if not uses_firebase():
        return True
    if not viewer_uid:
        return False
    if has_request_context() and is_admin():
        return True
    if is_household_personal_calendar(pc):
        return True
    if pc.owner_uid == viewer_uid:
        return True
    return PersonalCalendarShare.query.filter_by(
        personal_calendar_id=pc.id,
        grantee_uid=viewer_uid,
    ).first() is not None


def can_write_personal_calendar(pc: PersonalCalendar, viewer_uid: str | None = None) -> bool:
    viewer_uid = viewer_uid or _viewer_uid()
    if not can_view_personal_calendar(pc, viewer_uid):
        return False
    if not uses_firebase():
        return True
    if has_request_context() and is_admin():
        return True
    if is_household_personal_calendar(pc):
        return True
    if pc.owner_uid == viewer_uid:
        return True
    share = PersonalCalendarShare.query.filter_by(
        personal_calendar_id=pc.id,
        grantee_uid=viewer_uid,
        can_write=True,
    ).first()
    return share is not None


def visible_personal_calendar_ids(viewer_uid: str | None = None) -> set[int]:
    viewer_uid = viewer_uid or _viewer_uid()
    if not uses_firebase():
        return {pc.id for pc in PersonalCalendar.query.filter_by(archived=False).all()}
    if not viewer_uid:
        return set()
    ids = set()
    for pc in PersonalCalendar.query.filter_by(archived=False).all():
        if can_view_personal_calendar(pc, viewer_uid):
            ids.add(pc.id)
    return ids


def household_member_roster(viewer_uid: str | None = None) -> list[dict]:
    """Firebase household members known to HomeHub (for share pickers)."""
    from ..google_calendar.imports import HOUSEHOLD_OWNER_UID

    viewer_uid = viewer_uid or _viewer_uid()
    by_uid: dict[str, str] = {}

    for conn in CalendarConnection.query.order_by(CalendarConnection.firebase_email.asc()).all():
        uid = (conn.firebase_uid or '').strip()
        if uid:
            by_uid[uid] = conn.firebase_email or ''

    for pc in PersonalCalendar.query.filter_by(archived=False).all():
        uid = (pc.owner_uid or '').strip()
        if uid and uid != HOUSEHOLD_OWNER_UID:
            by_uid.setdefault(uid, '')

    for share in PersonalCalendarShare.query.all():
        uid = (share.grantee_uid or '').strip()
        if uid:
            by_uid.setdefault(uid, '')

    for (uid,) in db.session.query(Reminder.owner_uid).filter(
        Reminder.owner_uid.isnot(None),
        Reminder.owner_uid != '',
    ).distinct():
        uid = (uid or '').strip()
        if uid:
            by_uid.setdefault(uid, '')

    out = []
    for uid, email in sorted(by_uid.items(), key=lambda item: (item[1] or item[0]).lower()):
        label = email or uid
        out.append({'uid': uid, 'email': label})
    return out
