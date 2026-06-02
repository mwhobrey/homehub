from datetime import date

from app import create_app, db
from app.google_calendar.imports import ensure_household_calendar
from app.models import CalendarConnection, PersonalCalendar, Reminder


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
        ensure_household_calendar()
        for uid, email in (('u1', 'one@test.com'), ('u2', 'two@test.com'), ('u3', 'three@test.com')):
            db.session.add(CalendarConnection(firebase_uid=uid, firebase_email=email))
        db.session.commit()
    return app


def _login(client, uid='u1'):
    with client.session_transaction() as sess:
        sess['firebase_uid'] = uid
        sess['firebase_email'] = f'{uid}@test.com'


def test_household_members_endpoint():
    app = make_app()
    client = app.test_client()
    _login(client, 'u1')
    res = client.get('/api/calendar/household-members')
    assert res.status_code == 200
    body = res.get_json()
    assert body['ok'] is True
    uids = {m['uid'] for m in body['members']}
    assert 'u1' not in uids
    assert {'u2', 'u3'}.issubset(uids)

    app = make_app()
    client = app.test_client()
    for uid in ('u1', 'u2', 'u3'):
        _login(client, uid)
        body = client.get('/api/calendar/personal-calendars').get_json()
        assert body['ok'] is True
        household = [c for c in body['calendars'] if c.get('is_household')]
        assert len(household) == 1
        assert household[0]['name'] == 'Household'


def test_private_calendar_hidden_from_non_shared_member():
    app = make_app()
    client = app.test_client()
    _login(client, 'u1')
    created = client.post(
        '/api/calendar/personal-calendars',
        json={'name': 'Secret', 'color': '#111111'},
    ).get_json()
    pc_id = created['calendar']['id']

    with app.app_context():
        db.session.add(
            Reminder(
                title='Private event',
                date=date(2026, 6, 3),
                owner_uid='u1',
                personal_calendar_id=pc_id,
            )
        )
        db.session.commit()

    _login(client, 'u2')
    listed = client.get('/api/calendar/personal-calendars').get_json()
    ids = {c['id'] for c in listed['calendars']}
    assert pc_id not in ids

    reminders = client.get('/api/reminders?scope=month&date=2026-06-01').get_json()
    titles = {r['title'] for r in reminders.get('reminders', [])}
    assert 'Private event' not in titles


def test_shared_calendar_visible_to_grantee_only():
    app = make_app()
    client = app.test_client()
    _login(client, 'u1')
    pc_id = client.post(
        '/api/calendar/personal-calendars',
        json={'name': 'Shared Work', 'color': '#222222'},
    ).get_json()['calendar']['id']

    shares = client.put(
        f'/api/calendar/personal-calendars/{pc_id}/shares',
        json={'shares': [{'grantee_uid': 'u2', 'can_write': False}]},
    )
    assert shares.status_code == 200

    with app.app_context():
        db.session.add(
            Reminder(
                title='Shared event',
                date=date(2026, 6, 4),
                owner_uid='u1',
                personal_calendar_id=pc_id,
            )
        )
        db.session.commit()

    _login(client, 'u2')
    listed = client.get('/api/calendar/personal-calendars').get_json()
    assert pc_id in {c['id'] for c in listed['calendars']}
    shared = next(c for c in listed['calendars'] if c['id'] == pc_id)
    assert shared['is_owner'] is False
    assert shared['can_edit'] is False

    reminders = client.get('/api/reminders?scope=month&date=2026-06-01').get_json()
    assert 'Shared event' in {r['title'] for r in reminders.get('reminders', [])}

    _login(client, 'u3')
    listed_u3 = client.get('/api/calendar/personal-calendars').get_json()
    assert pc_id not in {c['id'] for c in listed_u3['calendars']}
    reminders_u3 = client.get('/api/reminders?scope=month&date=2026-06-01').get_json()
    assert 'Shared event' not in {r['title'] for r in reminders_u3.get('reminders', [])}


def test_cannot_delete_household_calendar():
    app = make_app()
    client = app.test_client()
    _login(client, 'u1')
    with app.app_context():
        household_id = ensure_household_calendar().id
    res = client.delete(f'/api/calendar/personal-calendars/{household_id}')
    assert res.status_code == 400
    assert 'household' in res.get_json()['error'].lower()


def test_share_write_allows_grantee_to_edit_calendar():
    app = make_app()
    client = app.test_client()
    _login(client, 'u1')
    pc_id = client.post(
        '/api/calendar/personal-calendars',
        json={'name': 'Collab', 'color': '#333333'},
    ).get_json()['calendar']['id']
    client.put(
        f'/api/calendar/personal-calendars/{pc_id}/shares',
        json={'shares': [{'grantee_uid': 'u2', 'can_write': True}]},
    )

    _login(client, 'u2')
    patched = client.patch(
        f'/api/calendar/personal-calendars/{pc_id}',
        json={'name': 'Collab Renamed'},
    )
    assert patched.status_code == 200
    assert patched.get_json()['calendar']['name'] == 'Collab Renamed'
