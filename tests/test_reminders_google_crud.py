from unittest.mock import patch

import pytest

from app import create_app, db
from app.models import CalendarConnection, LinkedCalendar, Reminder
from app.sensitive_store import encrypt_sensitive


def make_app():
    test_config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'HOMEHUB_CONFIG': {
            'auth': {
                'mode': 'firebase',
                'allowed_emails': ['alice@test.com'],
                'display_names': {'alice@test.com': 'Alice'},
            },
            'google_calendar': {'enabled': True, 'client_id': 'cid', 'client_secret': 'sec'},
            'reminders': {'calendar_start_day': 'sunday'},
        },
        'SECRET_KEY': 'test',
    }
    app = create_app(test_config)
    with app.app_context():
        db.create_all()
    return app


@pytest.fixture()
def app_client():
    app = make_app()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['firebase_uid'] = 'uid_alice'
        sess['firebase_email'] = 'alice@test.com'
        sess['display_name'] = 'Alice'
    return app, client


def _seed_calendars(app):
    with app.app_context():
        conn = CalendarConnection(
            firebase_uid='uid_alice',
            firebase_email='alice@test.com',
            refresh_token_enc=encrypt_sensitive('refresh-token'),
        )
        db.session.add(conn)
        db.session.flush()
        lc_default = LinkedCalendar(
            connection_id=conn.id,
            google_calendar_id='primary',
            summary='Primary',
            sync_enabled=True,
        )
        lc_school = LinkedCalendar(
            connection_id=conn.id,
            google_calendar_id='school_id',
            summary='School',
            sync_enabled=True,
        )
        db.session.add_all([lc_default, lc_school])
        db.session.flush()
        conn.default_linked_calendar_id = lc_default.id
        db.session.commit()
        return lc_default.id, lc_school.id


@patch('app.google_calendar.writes.push_reminder_create')
def test_create_uses_default_calendar(mock_push, app_client):
    app, client = app_client
    lc_default_id, _ = _seed_calendars(app)
    mock_push.return_value = True
    with app.app_context():
        r = client.post(
            '/api/reminders',
            json={'title': 'Test', 'date': '2026-06-15', 'creator': 'Alice'},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data['ok']
        rem = Reminder.query.get(data['reminder']['id'])
        assert rem.linked_calendar_id == lc_default_id
        mock_push.assert_called_once()


@patch('app.google_calendar.writes.push_reminder_create')
def test_create_explicit_calendar(mock_push, app_client):
    app, client = app_client
    _, lc_school_id = _seed_calendars(app)
    mock_push.return_value = True
    with app.app_context():
        r = client.post(
            '/api/reminders',
            json={
                'title': 'School event',
                'date': '2026-06-16',
                'linked_calendar_id': lc_school_id,
                'creator': 'Alice',
            },
        )
        assert r.status_code == 200
        rem = Reminder.query.get(r.get_json()['reminder']['id'])
        assert rem.linked_calendar_id == lc_school_id


def test_reject_foreign_calendar(app_client):
    app, client = app_client
    with app.app_context():
        conn_b = CalendarConnection(firebase_uid='uid_bob', firebase_email='bob@test.com')
        db.session.add(conn_b)
        db.session.flush()
        lc_bob = LinkedCalendar(
            connection_id=conn_b.id,
            google_calendar_id='bob_cal',
            summary='Bob',
        )
        db.session.add(lc_bob)
        db.session.commit()
        r = client.post(
            '/api/reminders',
            json={
                'title': 'Hack',
                'date': '2026-06-16',
                'linked_calendar_id': lc_bob.id,
                'creator': 'Alice',
            },
        )
        assert r.status_code == 400
