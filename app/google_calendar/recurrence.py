"""RRULE helpers for Google Calendar recurrence."""

from __future__ import annotations

from datetime import date

from ..models import RecurringReminder

_FREQ = {
    'day': 'DAILY',
    'week': 'WEEKLY',
    'month': 'MONTHLY',
    'year': 'YEARLY',
}


def rule_to_rrule(rr: RecurringReminder) -> str:
    unit = (getattr(rr, 'unit', None) or 'day').lower()
    if unit not in _FREQ:
        if rr.frequency == 'weekly':
            unit = 'week'
        elif rr.frequency == 'monthly':
            unit = 'month'
        else:
            unit = 'day'
    interval = int(getattr(rr, 'interval', None) or 1)
    if interval < 1:
        interval = 1
    parts = [f'FREQ={_FREQ[unit]}']
    if interval > 1:
        parts.append(f'INTERVAL={interval}')
    if rr.end_date:
        parts.append(f'UNTIL={rr.end_date.strftime("%Y%m%d")}T235959Z')
    return ';'.join(parts)


def rrule_line(rr: RecurringReminder) -> str:
    return f'RRULE:{rule_to_rrule(rr)}'
