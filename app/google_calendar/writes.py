"""Push local reminder changes to Google Calendar."""

from __future__ import annotations

import json

from flask import current_app

from ..models import CalendarSyncOutbox, LinkedCalendar, Reminder, db
from .acl import get_connection_for_uid, owns_linked_calendar
from .client import get_calendar_service
from .mapper import reminder_to_google_event


def _enqueue(reminder_id: int, operation: str, payload: dict | None = None) -> None:
    row = CalendarSyncOutbox(
        reminder_id=reminder_id,
        operation=operation,
        payload_json=json.dumps(payload or {}),
    )
    db.session.add(row)
    db.session.commit()


def push_reminder_create(reminder: Reminder, lc: LinkedCalendar) -> bool:
    conn = lc.connection
    if not conn:
        return False
    try:
        service = get_calendar_service(conn)
        tz = conn.time_zone or 'UTC'
        body = reminder_to_google_event(reminder, tz)
        created = (
            service.events()
            .insert(calendarId=lc.google_calendar_id, body=body)
            .execute()
        )
        reminder.google_event_id = created.get('id')
        reminder.google_etag = created.get('etag')
        reminder.google_updated = created.get('updated')
        reminder.google_recurring_event_id = created.get('recurringEventId')
        reminder.source = 'google'
        reminder.linked_calendar_id = lc.id
        reminder.owner_uid = conn.firebase_uid
        reminder.sync_status = 'synced'
        db.session.commit()
        return True
    except Exception:
        current_app.logger.exception('google push create failed')
        reminder.sync_status = 'pending_push'
        db.session.commit()
        _enqueue(reminder.id, 'create', {'linked_calendar_id': lc.id})
        return False


def push_reminder_update(reminder: Reminder, lc: LinkedCalendar) -> bool:
    if not reminder.google_event_id:
        return push_reminder_create(reminder, lc)
    conn = lc.connection
    if not conn:
        return False
    try:
        service = get_calendar_service(conn)
        tz = conn.time_zone or 'UTC'
        body = reminder_to_google_event(reminder, tz)
        updated = (
            service.events()
            .update(
                calendarId=lc.google_calendar_id,
                eventId=reminder.google_event_id,
                body=body,
            )
            .execute()
        )
        reminder.google_etag = updated.get('etag')
        reminder.google_updated = updated.get('updated')
        reminder.sync_status = 'synced'
        db.session.commit()
        return True
    except Exception:
        current_app.logger.exception('google push update failed')
        reminder.sync_status = 'pending_push'
        db.session.commit()
        _enqueue(reminder.id, 'update', {'linked_calendar_id': lc.id})
        return False


def push_reminder_delete(reminder: Reminder, lc: LinkedCalendar) -> bool:
    if not reminder.google_event_id:
        return True
    conn = lc.connection
    if not conn:
        return False
    try:
        service = get_calendar_service(conn)
        service.events().delete(
            calendarId=lc.google_calendar_id,
            eventId=reminder.google_event_id,
        ).execute()
        return True
    except Exception:
        current_app.logger.exception('google push delete failed')
        _enqueue(reminder.id, 'delete', {'linked_calendar_id': lc.id})
        return False


def push_reminder_move(
    reminder: Reminder,
    from_lc: LinkedCalendar,
    to_lc: LinkedCalendar,
) -> bool:
    if not reminder.google_event_id or not owns_linked_calendar(from_lc):
        reminder.linked_calendar_id = to_lc.id
        return push_reminder_update(reminder, to_lc)
    conn = from_lc.connection
    if not conn:
        return False
    try:
        service = get_calendar_service(conn)
        moved = (
            service.events()
            .move(
                calendarId=from_lc.google_calendar_id,
                eventId=reminder.google_event_id,
                destination=to_lc.google_calendar_id,
            )
            .execute()
        )
        reminder.google_event_id = moved.get('id')
        reminder.google_etag = moved.get('etag')
        reminder.google_updated = moved.get('updated')
        reminder.linked_calendar_id = to_lc.id
        reminder.sync_status = 'synced'
        db.session.commit()
        return push_reminder_update(reminder, to_lc)
    except Exception:
        current_app.logger.exception('google move failed; trying update only')
        reminder.linked_calendar_id = to_lc.id
        return push_reminder_update(reminder, to_lc)


def process_outbox_for_connection(conn_id: int, limit: int = 50) -> None:
    from ..models import CalendarConnection

    conn = CalendarConnection.query.get(conn_id)
    if not conn:
        return
    rows = (
        CalendarSyncOutbox.query.order_by(CalendarSyncOutbox.id.asc()).limit(limit).all()
    )
    for row in rows:
        reminder = Reminder.query.get(row.reminder_id) if row.reminder_id else None
        if not reminder:
            db.session.delete(row)
            continue
        if reminder.owner_uid and reminder.owner_uid != conn.firebase_uid:
            continue
        payload = {}
        try:
            payload = json.loads(row.payload_json or '{}')
        except Exception:
            pass
        lc_id = payload.get('linked_calendar_id') or reminder.linked_calendar_id
        lc = LinkedCalendar.query.get(lc_id) if lc_id else None
        if not lc or lc.connection_id != conn.id:
            db.session.delete(row)
            db.session.commit()
            continue
        ok = False
        if row.operation == 'create':
            ok = push_reminder_create(reminder, lc)
        elif row.operation == 'update':
            ok = push_reminder_update(reminder, lc)
        elif row.operation == 'delete':
            ok = push_reminder_delete(reminder, lc)
        elif row.operation == 'move':
            to_id = payload.get('to_linked_calendar_id')
            to_lc = LinkedCalendar.query.get(to_id) if to_id else None
            if to_lc:
                ok = push_reminder_move(reminder, lc, to_lc)
        if ok or reminder.sync_status == 'synced':
            db.session.delete(row)
        else:
            row.attempts = (row.attempts or 0) + 1
            row.last_error = 'retry'
        db.session.commit()
