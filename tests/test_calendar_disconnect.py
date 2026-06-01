"""Google Calendar disconnect and connection status."""

from unittest.mock import MagicMock, patch

import pytest

from app import create_app, db
from app.models import CalendarConnection, LinkedCalendar
from app.sensitive_store import encrypt_sensitive


def make_app():
    test_config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'HOMEHUB_CONFIG': {
            'auth': {
                'mode': 'firebase',
                'allowed_emails': ['alice@test.com'],
            },
            'google_calendar': {'enabled': True, 'client_id': 'cid', 'client_secret': 'sec'},
        },
        'SECRET_KEY': 'test',
    }
    app = create_app(test_config)
    with app.app_context():
        db.create_all()
    return app


@pytest.fixture()
def client():
    app = make_app()
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['firebase_uid'] = 'uid_alice'
        sess['firebase_email'] = 'alice@test.com'
    return app, c


def test_status_incomplete_without_tokens(client):
    app, c = client
    with app.app_context():
        db.session.add(
            CalendarConnection(
                firebase_uid='uid_alice',
                firebase_email='alice@test.com',
                oauth_state_nonce='abc',
            )
        )
        db.session.commit()
    r = c.get('/api/calendar/status')
    assert r.status_code == 200
    data = r.get_json()
    assert data['connected'] is False
    assert data.get('connection_incomplete') is True


def test_status_connected_with_tokens(client):
    app, c = client
    with app.app_context():
        db.session.add(
            CalendarConnection(
                firebase_uid='uid_alice',
                refresh_token_enc=encrypt_sensitive('rt'),
            )
        )
        db.session.commit()
    r = c.get('/api/calendar/status')
    data = r.get_json()
    assert data['connected'] is True


@patch('app.blueprints.calendar_sync._flow')
def test_oauth_start_stores_pkce_verifier(mock_flow_factory, client):
    _app, c = client
    mock_flow = MagicMock()
    mock_flow.authorization_url.return_value = ('https://accounts.google.com/o/oauth2/auth', 'state-nonce')
    mock_flow.code_verifier = 'pkce-verifier-1234567890123456789012345678901234567890'
    mock_flow_factory.return_value = mock_flow
    r = c.get('/auth/google/calendar/start', follow_redirects=False)
    assert r.status_code == 302
    with c.session_transaction() as sess:
        assert sess.get('google_calendar_oauth_code_verifier') == mock_flow.code_verifier
        assert sess.get('google_calendar_oauth_state')


def test_disconnect_removes_connection(client):
    app, c = client
    with app.app_context():
        conn = CalendarConnection(
            firebase_uid='uid_alice',
            refresh_token_enc=encrypt_sensitive('rt'),
        )
        db.session.add(conn)
        db.session.flush()
        db.session.add(
            LinkedCalendar(
                connection_id=conn.id,
                google_calendar_id='primary',
                summary='Primary',
            )
        )
        db.session.commit()
    r = c.post('/api/calendar/disconnect', json={'remove_google_reminders': False})
    assert r.status_code == 200
    assert r.get_json()['ok'] is True
    with app.app_context():
        assert CalendarConnection.query.filter_by(firebase_uid='uid_alice').first() is None
        assert LinkedCalendar.query.count() == 0
