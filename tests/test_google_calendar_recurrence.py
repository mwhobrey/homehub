"""Tests for RRULE generation."""

from datetime import date

from app.google_calendar.recurrence import rule_to_rrule, rrule_line
from app.models import RecurringReminder


def test_weekly_rrule():
    rr = RecurringReminder(title='Standup', interval=2, unit='week', start_date=date(2026, 6, 1))
    assert rule_to_rrule(rr) == 'FREQ=WEEKLY;INTERVAL=2'
    assert rrule_line(rr) == 'RRULE:FREQ=WEEKLY;INTERVAL=2'


def test_rrule_until():
    rr = RecurringReminder(
        title='Camp',
        interval=1,
        unit='day',
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 5),
    )
    assert 'UNTIL=20260705T235959Z' in rule_to_rrule(rr)
