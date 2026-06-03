from datetime import date

from app import create_app, db
from app.models import TodoList, TodoItem, TodoListShare, Reminder


def make_app():
    test_config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'HOMEHUB_CONFIG': {
            'auth': {'mode': 'legacy'},
            'feature_toggles': {'todo_list': True},
            'family_members': ['Alice', 'Bob'],
        },
        'SECRET_KEY': 'test',
    }
    app = create_app(test_config)
    with app.app_context():
        db.create_all()
    return app


def test_todo_list_household_visible_to_all():
    app = make_app()
    client = app.test_client()
    res = client.post(
        '/api/todo-lists',
        json={'name': 'Groceries', 'visibility': 'household', 'creator': 'Alice'},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body['ok'] is True
    list_id = body['list']['id']

    res2 = client.get('/api/todo-lists')
    assert res2.get_json()['ok'] is True
    assert any(l['id'] == list_id for l in res2.get_json()['lists'])

    item_res = client.post(
        f'/api/todo-lists/{list_id}/items',
        json={'description': 'Milk', 'creator': 'Bob', 'tags': ['dairy']},
    )
    assert item_res.get_json()['ok'] is True

    items = client.get(f'/api/todo-lists/{list_id}/items').get_json()
    assert len(items['items']) == 1
    assert items['items'][0]['description'] == 'Milk'


def test_todo_list_calendars_includes_household_default():
    app = make_app()
    res = app.test_client().get('/api/todo-lists/calendars')
    body = res.get_json()
    assert body['ok'] is True
    assert body['calendars']
    assert body.get('default_calendar_id')
    assert any(c.get('is_household') for c in body['calendars'])
    assert any(c.get('is_default') for c in body['calendars'])


def test_todo_item_due_date_syncs_to_personal_calendar():
    app = make_app()
    with app.app_context():
        from app.google_calendar.imports import ensure_household_calendar
        pc = ensure_household_calendar()
        pc_id = pc.id
    client = app.test_client()
    due = date.today().isoformat()
    created = client.post(
        '/api/todo-lists',
        json={
            'name': 'Bills',
            'visibility': 'household',
            'creator': 'Alice',
            'personal_calendar_id': pc_id,
        },
    ).get_json()
    assert created['ok'] is True
    list_id = created['list']['id']
    item_res = client.post(
        f'/api/todo-lists/{list_id}/items',
        json={'description': 'Pay electric', 'due_date': due, 'creator': 'Alice'},
    )
    assert item_res.get_json()['ok'] is True
    with app.app_context():
        item = TodoItem.query.filter_by(description='Pay electric').first()
        assert item and item.reminder_id
        item_id = item.id
        reminder_id = item.reminder_id
        r = Reminder.query.get(reminder_id)
        assert r is not None
        assert r.date.isoformat() == due
        assert r.personal_calendar_id == pc_id
        assert r.all_day is True
        assert r.category == 'todo'
    toggled = client.post(f'/api/todo-items/{item_id}/toggle', json={})
    assert toggled.get_json()['ok'] is True
    with app.app_context():
        item = TodoItem.query.get(item_id)
        assert item.done
        assert item.reminder_id is None
        assert Reminder.query.get(reminder_id) is None


def test_private_list_firebase_sharing():
    test_config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'HOMEHUB_CONFIG': {
            'auth': {'mode': 'firebase', 'display_names': {}},
            'feature_toggles': {'todo_list': True},
        },
        'SECRET_KEY': 'test',
    }
    app = create_app(test_config)
    with app.app_context():
        db.create_all()
        from app.models import CalendarConnection
        for uid, email in (('u1', 'one@test.com'), ('u2', 'two@test.com')):
            db.session.add(CalendarConnection(firebase_uid=uid, firebase_email=email))
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['firebase_uid'] = 'u1'
        sess['firebase_email'] = 'one@test.com'
        sess['display_name'] = 'One'

    created = client.post(
        '/api/todo-lists',
        json={
            'name': 'Secret',
            'visibility': 'private',
            'shared_with': [{'grantee_uid': 'u2', 'can_write': True}],
        },
    ).get_json()
    assert created['ok'] is True
    list_id = created['list']['id']

    with client.session_transaction() as sess:
        sess['firebase_uid'] = 'u2'
        sess['firebase_email'] = 'two@test.com'

    listed = client.get('/api/todo-lists').get_json()
    assert any(l['id'] == list_id for l in listed['lists'])

    with client.session_transaction() as sess:
        sess.clear()
        sess['firebase_uid'] = 'u3'
        sess['firebase_email'] = 'three@test.com'

    hidden = client.get('/api/todo-lists').get_json()
    assert not any(l['id'] == list_id for l in hidden['lists'])
