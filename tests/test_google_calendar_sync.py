from datetime import date
from unittest.mock import MagicMock, patch

from app import create_app, db
from app.models import CalendarConnection, LinkedCalendar, Reminder, CalendarImportMapping, PersonalCalendar, CategoryImportMapping
from app.google_calendar.sync import pull_calendar, sync_connection


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


def test_sync_connection_skips_pull_when_manual():
    app = make_app()
    with app.app_context():
        conn = CalendarConnection(
            firebase_uid='u1',
            firebase_email='a@t.com',
            refresh_token_enc='x',
            sync_mode='manual',
        )
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
        with patch('app.google_calendar.sync.process_outbox_for_connection') as outbox_mock, patch(
            'app.google_calendar.sync.pull_calendar'
        ) as pull_mock:
            sync_connection(conn)
        outbox_mock.assert_not_called()
        pull_mock.assert_not_called()
        with patch('app.google_calendar.sync.process_outbox_for_connection') as outbox_mock, patch(
            'app.google_calendar.sync.pull_calendar'
        ) as pull_mock:
            sync_connection(conn, force_pull=True)
        outbox_mock.assert_not_called()
        pull_mock.assert_called_once()


def test_sync_connection_skips_outbox_when_import_only():
    app = make_app()
    with app.app_context():
        conn = CalendarConnection(
            firebase_uid='u1',
            firebase_email='a@t.com',
            refresh_token_enc='x',
            sync_mode='import_only',
        )
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
        with patch('app.google_calendar.sync.process_outbox_for_connection') as outbox_mock, patch(
            'app.google_calendar.sync.pull_calendar'
        ) as pull_mock:
            sync_connection(conn)
        outbox_mock.assert_not_called()
        pull_mock.assert_called_once()


def test_pull_applies_import_mapping_and_category_mapping():
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
        db.session.flush()
        pc = PersonalCalendar(owner_uid='u1', name='My Calendar', color='#2563eb')
        db.session.add(pc)
        db.session.flush()
        db.session.add(
            CalendarImportMapping(
                connection_id=conn.id,
                linked_calendar_id=lc.id,
                personal_calendar_id=pc.id,
                import_enabled=True,
                import_color='#ff00ff',
            )
        )
        db.session.add(
            CategoryImportMapping(
                connection_id=conn.id,
                linked_calendar_id=lc.id,
                source_key='default',
                source_label='Default',
                target_key='family',
                target_label='Family',
                target_color='#00ff00',
            )
        )
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
        assert rem.personal_calendar_id == pc.id
        assert rem.color == '#ff00ff'
        assert rem.category == 'family'
