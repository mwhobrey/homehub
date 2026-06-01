"""Map Google Calendar events to Reminder rows and back."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore

from ..models import Reminder


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


def event_to_reminder_fields(event: dict, tz_name: str) -> dict:
    start = event.get('start') or {}
    end = event.get('end') or {}
    if 'date' in start:
        d = date.fromisoformat(start['date'])
        tval = None
        all_day = True
    else:
        d, tval, all_day = _parse_google_dt(start.get('dateTime', ''), tz_name)
    desc = event.get('description') or ''
    return {
        'title': (event.get('summary') or 'Untitled')[:256],
        'description': desc,
        'date': d,
        'time': tval,
        'all_day': all_day,
        'google_event_id': event.get('id'),
        'google_recurring_event_id': event.get('recurringEventId'),
        'google_etag': event.get('etag'),
        'google_updated': event.get('updated'),
        'source': 'google',
    }


def _zone(tz_name: str):
    if ZoneInfo is not None:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    return timezone.utc


def reminder_to_google_event(reminder: Reminder, tz_name: str) -> dict:
    body: dict = {
        'summary': reminder.title,
        'description': reminder.description or '',
    }
    if reminder.all_day:
        body['start'] = {'date': reminder.date.isoformat()}
        end_d = reminder.date + timedelta(days=1)
        body['end'] = {'date': end_d.isoformat()}
    elif reminder.time:
        hh, mm = reminder.time.split(':', 1)
        start_dt = datetime(
            reminder.date.year,
            reminder.date.month,
            reminder.date.day,
            int(hh),
            int(mm),
            tzinfo=_zone(tz_name),
        )
        end_dt = start_dt + timedelta(hours=1)
        body['start'] = {'dateTime': start_dt.isoformat(), 'timeZone': tz_name}
        body['end'] = {'dateTime': end_dt.isoformat(), 'timeZone': tz_name}
    else:
        body['start'] = {'date': reminder.date.isoformat()}
        end_d = reminder.date + timedelta(days=1)
        body['end'] = {'date': end_d.isoformat()}
    return body
