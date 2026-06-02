"""Map Google Calendar events to Reminder rows and back."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore

from ..models import RecurringReminder, Reminder
from .recurrence import rrule_line


def _parse_google_dt(value: str, tz_name: str) -> tuple[date, str | None, bool]:
    if not value:
        return date.today(), None, True
    if 'T' in value:
        try:
            if value.endswith('Z'):
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            else:
                dt = datetime.fromisoformat(value)
            tz = None
            if ZoneInfo is not None:
                try:
                    tz = ZoneInfo(tz_name)
                except Exception:
                    tz = timezone.utc
            else:
                tz = timezone.utc
            if dt.tzinfo is None and tz:
                dt = dt.replace(tzinfo=tz)
            local = dt.astimezone(tz) if tz else dt
            return local.date(), f'{local.hour:02d}:{local.minute:02d}', False
        except Exception:
            return date.today(), None, False
    try:
        return date.fromisoformat(value[:10]), None, True
    except Exception:
        return date.today(), None, True


def _zone(tz_name: str):
    if ZoneInfo is not None:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    return timezone.utc


def _serialize_attendees(event: dict) -> str | None:
    attendees = event.get('attendees') or []
    if not attendees:
        return None
    out = []
    for a in attendees:
        email = (a.get('email') or '').strip()
        if not email:
            continue
        out.append({
            'email': email,
            'displayName': a.get('displayName') or '',
            'optional': bool(a.get('optional')),
            'responseStatus': a.get('responseStatus') or 'needsAction',
        })
    return json.dumps(out) if out else None


def parse_attendees_payload(raw) -> list[dict]:
    if raw is None:
        return []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        if raw.startswith('['):
            try:
                items = json.loads(raw)
            except Exception:
                items = [{'email': e.strip()} for e in raw.split(',') if e.strip()]
        else:
            items = [{'email': e.strip()} for e in raw.split(',') if e.strip()]
    else:
        return []
    out = []
    for item in items:
        if isinstance(item, str):
            email = item.strip()
            if email:
                out.append({'email': email})
        elif isinstance(item, dict):
            email = (item.get('email') or '').strip()
            if email:
                out.append({
                    'email': email,
                    'displayName': (item.get('displayName') or item.get('name') or '').strip(),
                    'optional': bool(item.get('optional')),
                })
    return out


def attendees_for_google(reminder: Reminder) -> list[dict]:
    raw = getattr(reminder, 'attendees_json', None)
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for a in data:
        if not isinstance(a, dict):
            continue
        email = (a.get('email') or '').strip()
        if not email:
            continue
        entry = {'email': email}
        if a.get('optional'):
            entry['optional'] = True
        if a.get('displayName'):
            entry['displayName'] = a['displayName']
        out.append(entry)
    return out


def reminder_tz(reminder: Reminder, default_tz: str) -> str:
    tz = getattr(reminder, 'time_zone', None) or default_tz
    return tz or 'UTC'


def event_to_reminder_fields(event: dict, tz_name: str) -> dict:
    start = event.get('start') or {}
    end = event.get('end') or {}
    event_tz = start.get('timeZone') or end.get('timeZone') or tz_name
    if 'date' in start:
        d = date.fromisoformat(start['date'])
        tval = None
        all_day = True
    else:
        d, tval, all_day = _parse_google_dt(start.get('dateTime', ''), event_tz)
    end_date = None
    end_time = None
    if 'date' in end:
        try:
            end_exclusive = date.fromisoformat(end['date'][:10])
            end_date = end_exclusive - timedelta(days=1)
        except Exception:
            pass
    elif end.get('dateTime'):
        end_date, end_time, _ = _parse_google_dt(end.get('dateTime', ''), event_tz)
    desc = event.get('description') or ''
    return {
        'title': (event.get('summary') or 'Untitled')[:256],
        'description': desc,
        'date': d,
        'time': tval,
        'end_date': end_date,
        'end_time': end_time,
        'all_day': all_day,
        'time_zone': event_tz,
        'attendees_json': _serialize_attendees(event),
        'google_event_id': event.get('id'),
        'google_recurring_event_id': event.get('recurringEventId'),
        'google_etag': event.get('etag'),
        'google_updated': event.get('updated'),
        'source': 'google',
    }


def infer_source_category(event: dict) -> tuple[str, str]:
    event_type = (event.get('eventType') or '').strip().lower()
    if event_type:
        return event_type, event_type.replace('_', ' ').title()
    color_id = (event.get('colorId') or '').strip()
    if color_id:
        return f'google_color_{color_id}', f'Google Color {color_id}'
    return 'default', 'Default'


def reminder_to_google_event(reminder: Reminder, tz_name: str) -> dict:
    tz = reminder_tz(reminder, tz_name)
    body: dict = {
        'summary': reminder.title,
        'description': reminder.description or '',
    }
    attendees = attendees_for_google(reminder)
    if attendees:
        body['attendees'] = attendees
    if reminder.all_day:
        body['start'] = {'date': reminder.date.isoformat()}
        end_d = (getattr(reminder, 'end_date', None) or reminder.date) + timedelta(days=1)
        body['end'] = {'date': end_d.isoformat()}
    elif reminder.time:
        hh, mm = reminder.time.split(':', 1)
        start_dt = datetime(
            reminder.date.year,
            reminder.date.month,
            reminder.date.day,
            int(hh),
            int(mm),
            tzinfo=_zone(tz),
        )
        if getattr(reminder, 'end_time', None) and reminder.end_time:
            eh, em = reminder.end_time.split(':', 1)
            end_day = getattr(reminder, 'end_date', None) or reminder.date
            end_dt = datetime(
                end_day.year, end_day.month, end_day.day,
                int(eh), int(em), tzinfo=_zone(tz),
            )
        else:
            end_dt = start_dt + timedelta(hours=1)
        body['start'] = {'dateTime': start_dt.isoformat(), 'timeZone': tz}
        body['end'] = {'dateTime': end_dt.isoformat(), 'timeZone': tz}
    else:
        body['start'] = {'date': reminder.date.isoformat()}
        end_d = reminder.date + timedelta(days=1)
        body['end'] = {'date': end_d.isoformat()}
    return body


def recurring_rule_to_google_event(rr: RecurringReminder, tz_name: str) -> dict:
    """Build Google Calendar master recurring event body."""
    fake = Reminder(
        date=rr.start_date or date.today(),
        title=rr.title,
        description=rr.description or '',
        time=rr.time,
        all_day=not bool(rr.time),
        end_date=rr.end_date,
    )
    if getattr(rr, 'time_zone', None):
        fake.time_zone = rr.time_zone
    body = reminder_to_google_event(fake, tz_name)
    body['recurrence'] = [rrule_line(rr)]
    return body
