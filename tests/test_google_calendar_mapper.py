from datetime import date

from app.google_calendar.mapper import event_to_reminder_fields, reminder_to_google_event
from app.models import Reminder


def test_all_day_event():
    event = {
        'id': 'evt1',
        'summary': 'Holiday',
        'start': {'date': '2026-06-01'},
        'end': {'date': '2026-06-02'},
        'etag': '"x"',
        'updated': '2026-05-01T00:00:00Z',
    }
    fields = event_to_reminder_fields(event, 'America/Chicago')
    assert fields['date'] == date(2026, 6, 1)
    assert fields['time'] is None
    assert fields['all_day'] is True
    assert fields['google_event_id'] == 'evt1'


def test_timed_event():
    event = {
        'id': 'evt2',
        'summary': 'Meeting',
        'start': {'dateTime': '2026-06-01T20:30:00Z'},
        'end': {'dateTime': '2026-06-01T21:30:00Z'},
    }
    fields = event_to_reminder_fields(event, 'UTC')
    assert fields['date'] == date(2026, 6, 1)
    assert fields['time'] == '20:30'
    assert fields['all_day'] is False


def test_reminder_to_google_all_day():
    r = Reminder(date=date(2026, 6, 1), title='X', all_day=True)
    body = reminder_to_google_event(r, 'UTC')
    assert body['start']['date'] == '2026-06-01'
