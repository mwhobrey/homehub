from datetime import date
from unittest.mock import MagicMock, patch

from app import create_app, db
from app.models import CalendarConnection, LinkedCalendar, Reminder
from app.google_calendar.sync import pull_calendar


def make_app():
    test_config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'HOMEHUB_CONFIG': {
            'google_calendar': {'enabled': True},
            'auth': {'display_names': {}},
        },
        'SECRET_KEY': 'test',
    }
    app = create_app(test_config)
    with app.app_context():
        db.create_all()
    return app


def test_pull_upserts_event():
    app = make_app()
    with app.app_context():
        conn = CalendarConnection(firebase_uid='u1', firebase_email='a@t.com', refresh_token_enc='x')
        db.session.add(conn)
        db.session.flush()
        lc = LinkedCalendar(
            connection_id=conn.id,
            google_calendar_id='cal1',
            summary='Cal',
            sync_enabled=True,
        )
        db.session.add(lc)
        db.session.commit()

        mock_service = MagicMock()
        mock_events = mock_service.events.return_value
        mock_list = mock_events.list.return_value
        mock_list.execute.return_value = {
            'items': [
                {
                    'id': 'e1',
                    'summary': 'From Google',
                    'start': {'date': '2026-07-04'},
                    'end': {'date': '2026-07-05'},
                    'etag': '"1"',
                    'updated': '2026-06-01T12:00:00Z',
                }
            ],
            'nextSyncToken': 'token123',
        }

        with patch('app.google_calendar.sync.get_calendar_service', return_value=mock_service):
            pull_calendar(lc)

        rem = Reminder.query.filter_by(google_event_id='e1').first()
        assert rem is not None
        assert rem.title == 'From Google'
        assert rem.date == date(2026, 7, 4)
        assert lc.sync_token == 'token123'
