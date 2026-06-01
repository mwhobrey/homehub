"""Pull Google Calendar changes and process outbound sync."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import current_app

from ..models import (
    CalendarConnection,
    CalendarDisplayPref,
    LinkedCalendar,
    Reminder,
    db,
)
from ..user_context import current_display_name
from .client import get_calendar_service
from .mapper import event_to_reminder_fields
from .writes import process_outbox_for_connection

_sync_locks: set[int] = set()


def _sync_window() -> tuple[str, str]:
    today = date.today()
    start = today - timedelta(days=365)
    end = today + timedelta(days=365)
    return start.isoformat() + 'T00:00:00Z', end.isoformat() + 'T23:59:59Z'


def pull_calendar(lc: LinkedCalendar) -> None:
    conn = lc.connection
    if not conn or not lc.sync_enabled:
        return
    tz = conn.time_zone or 'UTC'
    try:
        service = get_calendar_service(conn)
        kwargs = {
            'calendarId': lc.google_calendar_id,
            'singleEvents': True,
            'maxResults': 2500,
        }
        if lc.sync_token:
            kwargs['syncToken'] = lc.sync_token
        else:
            tmin, tmax = _sync_window()
            kwargs['timeMin'] = tmin
            kwargs['timeMax'] = tmax
        try:
            resp = service.events().list(**kwargs).execute()
        except Exception as exc:
            if '410' in str(exc) or 'fullSyncRequired' in str(exc):
                lc.sync_token = None
                db.session.commit()
                tmin, tmax = _sync_window()
                resp = (
                    service.events()
                    .list(
                        calendarId=lc.google_calendar_id,
                        singleEvents=True,
                        timeMin=tmin,
                        timeMax=tmax,
                        maxResults=2500,
                    )
                    .execute()
                )
            else:
                raise
        for event in resp.get('items') or []:
            if event.get('status') == 'cancelled':
                _delete_local_event(lc, event.get('id'))
                continue
            _upsert_event(lc, conn, event, tz)
        if resp.get('nextSyncToken'):
            lc.sync_token = resp['nextSyncToken']
        lc.last_sync_at = datetime.utcnow()
        lc.last_sync_error = None
        db.session.commit()
    except Exception as exc:
        lc.last_sync_error = str(exc)[:500]
        db.session.commit()
        current_app.logger.exception('pull_calendar failed for %s', lc.id)


def _delete_local_event(lc: LinkedCalendar, google_event_id: str | None) -> None:
    if not google_event_id:
        return
    Reminder.query.filter_by(
        linked_calendar_id=lc.id, google_event_id=google_event_id
    ).delete(synchronize_session=False)
    db.session.commit()


def _upsert_event(lc: LinkedCalendar, conn: CalendarConnection, event: dict, tz: str) -> None:
    eid = event.get('id')
    if not eid:
        return
    existing = Reminder.query.filter_by(
        linked_calendar_id=lc.id, google_event_id=eid
    ).first()
    fields = event_to_reminder_fields(event, tz)
    display = conn.firebase_email or ''
    names = (current_app.config.get('HOMEHUB_CONFIG') or {}).get('auth', {}).get(
        'display_names', {}
    )
    if conn.firebase_email and conn.firebase_email.lower() in names:
        display = names[conn.firebase_email.lower()]
    if existing:
        if existing.sync_status == 'pending_push':
            return
        g_updated = fields.get('google_updated') or ''
        if existing.google_updated and g_updated and existing.google_updated == g_updated:
            return
        if (
            existing.updated_at
            and existing.google_updated
            and existing.google_updated != g_updated
            and existing.sync_status not in ('synced', 'conflict')
        ):
            existing.sync_status = 'conflict'
        for k, v in fields.items():
            if k.startswith('google_') or k in ('title', 'description', 'date', 'time', 'all_day', 'source'):
                setattr(existing, k, v)
        existing.sync_status = existing.sync_status or 'synced'
        if existing.sync_status == 'conflict' and fields.get('google_updated') != existing.google_updated:
            pass
        else:
            existing.sync_status = 'synced'
        db.session.commit()
        return
    r = Reminder(
        creator=display or conn.firebase_email or 'Google',
        owner_uid=conn.firebase_uid,
        linked_calendar_id=lc.id,
        sync_status='synced',
        **fields,
    )
    db.session.add(r)
    db.session.commit()


def sync_connection(conn: CalendarConnection) -> None:
    if conn.id in _sync_locks:
        return
    _sync_locks.add(conn.id)
    try:
        process_outbox_for_connection(conn.id)
        for lc in LinkedCalendar.query.filter_by(connection_id=conn.id).all():
            if lc.sync_enabled:
                pull_calendar(lc)
        conn.last_sync_at = datetime.utcnow()
        db.session.commit()
    finally:
        _sync_locks.discard(conn.id)


def sync_all_connections() -> None:
    for conn in CalendarConnection.query.all():
        try:
            sync_connection(conn)
        except Exception:
            current_app.logger.exception('sync_connection failed %s', conn.id)


def sync_connection_for_uid(uid: str) -> None:
    conn = CalendarConnection.query.filter_by(firebase_uid=uid).first()
    if conn:
        sync_connection(conn)


def ensure_display_prefs_for_viewer(viewer_uid: str, lc: LinkedCalendar) -> None:
    pref = CalendarDisplayPref.query.filter_by(
        viewer_uid=viewer_uid, linked_calendar_id=lc.id
    ).first()
    if not pref:
        db.session.add(
            CalendarDisplayPref(viewer_uid=viewer_uid, linked_calendar_id=lc.id, visible=True)
        )
        db.session.commit()
