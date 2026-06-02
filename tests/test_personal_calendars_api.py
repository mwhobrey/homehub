from app import create_app, db
from app.google_calendar.imports import ensure_household_calendar
from app.models import PersonalCalendar


def make_app():
    test_config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'HOMEHUB_CONFIG': {
            'google_calendar': {'enabled': True},
            'auth': {'mode': 'firebase', 'display_names': {}},
        },
        'SECRET_KEY': 'test',
    }
    app = create_app(test_config)
    with app.app_context():
        db.create_all()
    return app


def _login(client, uid='u1'):
    with client.session_transaction() as sess:
        sess['firebase_uid'] = uid
        sess['firebase_email'] = f'{uid}@example.com'


def test_create_personal_calendar_with_shares():
    app = make_app()
    client = app.test_client()
    _login(client, 'u1')
    with app.app_context():
        from app.models import CalendarConnection
        db.session.add(CalendarConnection(firebase_uid='u2', firebase_email='two@test.com'))
        db.session.commit()
    res = client.post(
        '/api/calendar/personal-calendars',
        json={
            'name': 'Shared at birth',
            'color': '#6366f1',
            'shares': [{'grantee_uid': 'u2', 'can_write': True}],
        },
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body['ok'] is True
    pc_id = body['calendar']['id']
    assert len(body['calendar']['shared_with']) == 1
    assert body['calendar']['shared_with'][0]['grantee_uid'] == 'u2'
    assert body['calendar']['shared_with'][0]['can_write'] is True
    with app.app_context():
        from app.models import PersonalCalendarShare
        row = PersonalCalendarShare.query.filter_by(personal_calendar_id=pc_id, grantee_uid='u2').first()
        assert row is not None
        assert row.can_write is True


def test_personal_calendar_crud():
    app = make_app()
    client = app.test_client()
    _login(client)

    listed = client.get('/api/calendar/personal-calendars')
    assert listed.status_code == 200
    body = listed.get_json()
    assert body['ok'] is True
    assert any(c.get('is_household') for c in body['calendars'])

    alpha = client.post(
        '/api/calendar/personal-calendars',
        json={'name': 'Alpha', 'color': '#10b981'},
    )
    assert alpha.status_code == 200
    beta = client.post(
        '/api/calendar/personal-calendars',
        json={'name': 'Beta', 'color': '#6366f1'},
    )
    assert beta.status_code == 200
    beta_id = beta.get_json()['calendar']['id']
    assert beta.get_json()['calendar']['visibility'] == 'private'

    patched = client.patch(
        f'/api/calendar/personal-calendars/{beta_id}',
        json={'name': 'Beta Projects'},
    )
    assert patched.status_code == 200
    assert patched.get_json()['calendar']['name'] == 'Beta Projects'

    listed_after = client.get('/api/calendar/personal-calendars').get_json()
    private_count = sum(1 for c in listed_after['calendars'] if not c.get('is_household'))
    assert private_count >= 2

    deleted = client.delete(f'/api/calendar/personal-calendars/{beta_id}')
    assert deleted.status_code == 200
    with app.app_context():
        row = PersonalCalendar.query.get(beta_id)
        assert row.archived is True


def test_personal_calendar_cannot_delete_household():
    app = make_app()
    client = app.test_client()
    _login(client)
    with app.app_context():
        household_id = ensure_household_calendar().id
    blocked = client.delete(f'/api/calendar/personal-calendars/{household_id}')
    assert blocked.status_code == 400
    assert 'household' in blocked.get_json()['error'].lower()