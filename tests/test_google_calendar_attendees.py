"""Attendee parsing and mapping."""

from app.google_calendar.mapper import (
    attendees_for_google,
    event_to_reminder_fields,
    parse_attendees_payload,
)
from app.models import Reminder


def test_parse_attendees_comma_string():
    out = parse_attendees_payload('a@x.com, b@y.com')
    assert len(out) == 2
    assert out[0]['email'] == 'a@x.com'


def test_attendees_round_trip():
    r = Reminder(
        date=__import__('datetime').date(2026, 6, 1),
        title='Meet',
        attendees_json='[{"email":"guest@test.com","optional":true}]',
    )
    g = attendees_for_google(r)
    assert g[0]['email'] == 'guest@test.com'
    assert g[0]['optional'] is True


def test_pull_attendees_from_google_event():
    event = {
        'summary': 'Sync',
        'start': {'dateTime': '2026-06-01T15:00:00Z'},
        'end': {'dateTime': '2026-06-01T16:00:00Z'},
        'attendees': [{'email': 'bob@test.com', 'responseStatus': 'accepted'}],
    }
    fields = event_to_reminder_fields(event, 'UTC')
    assert fields['attendees_json']
    assert 'bob@test.com' in fields['attendees_json']
