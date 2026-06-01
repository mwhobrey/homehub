"""Calendar page route and schedule field serialization."""

import pytest

from app import create_app, db


def make_app(**overrides):
    cfg = {
        'admin_name': 'Administrator',
        'family_members': ['Alice'],
        'feature_toggles': {'calendar': True},
        'reminders': {'calendar_start_day': 'monday'},
    }
    cfg.update(overrides.get('HOMEHUB_CONFIG', {}))
    test_config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'HOMEHUB_CONFIG': cfg,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test',
    }
    test_config.update({k: v for k, v in overrides.items() if k != 'HOMEHUB_CONFIG'})
    app = create_app(test_config)
    with app.app_context():
        db.create_all()
    return app


@pytest.fixture()
def client():
    return make_app().test_client()


def test_calendar_page_renders(client):
    resp = client.get('/calendar')
    assert resp.status_code == 200
    assert b'calMonthGrid' in resp.data
    assert b'calendar_app.js' in resp.data


def test_calendar_page_redirect_when_disabled(client):
    app = make_app(HOMEHUB_CONFIG={
        'admin_name': 'Administrator',
        'family_members': ['Alice'],
        'feature_toggles': {'calendar': False},
    })
    resp = app.test_client().get('/calendar')
    assert resp.status_code == 302
    assert '/calendar' not in (resp.location or '')


def test_reminder_serialize_includes_schedule(client):
    created = client.post(
        '/api/reminders',
        json={
            'title': 'Trip',
            'date': '2026-06-01',
            'end_date': '2026-06-03',
            'all_day': True,
            'creator': 'Alice',
        },
    )
    assert created.status_code == 200
    rid = created.get_json()['reminder']['id']
    resp = client.get('/api/reminders', query_string={'scope': 'month', 'date': '2026-06-01'})
    assert resp.status_code == 200
    data = resp.get_json()
    item = next(x for x in data['reminders'] if x['id'] == rid)
    assert item['end_date'] == '2026-06-03'
    assert item['all_day'] is True


def test_reminder_custom_color_round_trip(client):
    created = client.post(
        '/api/reminders',
        json={
            'title': 'Painted',
            'date': '2026-06-10',
            'creator': 'Alice',
            'color': '#aabbcc',
        },
    )
    assert created.status_code == 200
    rid = created.get_json()['reminder']['id']
    assert created.get_json()['reminder']['color'] == '#aabbcc'
    updated = client.patch(
        f'/api/reminders/{rid}',
        json={'creator': 'Alice', 'color': '#112233'},
    )
    assert updated.get_json()['reminder']['color'] == '#112233'


def test_multiday_event_in_month_scope(client):
    client.post(
        '/api/reminders',
        json={
            'title': 'Conference',
            'date': '2026-05-28',
            'end_date': '2026-06-02',
            'all_day': True,
            'creator': 'Alice',
        },
    )
    resp = client.get('/api/reminders', query_string={'scope': 'month', 'date': '2026-06-01'})
    titles = [r['title'] for r in resp.get_json()['reminders']]
    assert 'Conference' in titles
