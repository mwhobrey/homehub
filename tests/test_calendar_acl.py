from app import create_app, db
from app.models import CalendarConnection, CalendarShare, LinkedCalendar, Reminder
from app.google_calendar.acl import can_view_linked_calendar, is_calendar_visible_to_viewer


def make_app():
    test_config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'HOMEHUB_CONFIG': {
            'auth': {'mode': 'firebase', 'allowed_emails': ['a@test.com', 'b@test.com', 'c@test.com']},
            'google_calendar': {'enabled': True, 'client_id': 'x', 'client_secret': 'y'},
        },
        'SECRET_KEY': 'test',
    }
    app = create_app(test_config)
    with app.app_context():
        db.create_all()
    return app


def test_private_calendar_not_visible_to_other():
    app = make_app()
    with app.app_context():
        conn_a = CalendarConnection(firebase_uid='uid_a', firebase_email='a@test.com')
        db.session.add(conn_a)
        db.session.flush()
        lc = LinkedCalendar(
            connection_id=conn_a.id,
            google_calendar_id='cal_adults',
            summary='Adults',
            visibility='private',
        )
        db.session.add(lc)
        db.session.commit()
        assert can_view_linked_calendar(lc, 'uid_a') is True
        assert can_view_linked_calendar(lc, 'uid_b') is False


def test_custom_share_grants_view():
    app = make_app()
    with app.app_context():
        conn_a = CalendarConnection(firebase_uid='uid_a', firebase_email='a@test.com')
        db.session.add(conn_a)
        db.session.flush()
        lc = LinkedCalendar(
            connection_id=conn_a.id,
            google_calendar_id='cal_adults',
            summary='Adults',
            visibility='custom',
        )
        db.session.add(lc)
        db.session.flush()
        db.session.add(CalendarShare(linked_calendar_id=lc.id, grantee_uid='uid_b', can_write=False))
        db.session.commit()
        assert can_view_linked_calendar(lc, 'uid_b') is True
        assert can_view_linked_calendar(lc, 'uid_c') is False
