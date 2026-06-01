"""Reminder category storage and API."""

import json

import pytest

from app import create_app, db
from app.reminder_categories import (
    load_reminder_categories,
    normalize_category_list,
    save_reminder_categories,
    slugify_category_key,
)


def make_app(categories=None):
    cfg = {
        'admin_name': 'Administrator',
        'family_members': ['Alice'],
        'reminders': {
            'categories': categories
            or [
                {'key': 'health', 'label': 'Health', 'color': '#dc2626'},
                {'key': 'bills', 'label': 'Bills', 'color': '#0d9488'},
            ],
        },
    }
    test_config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'HOMEHUB_CONFIG': cfg,
        'SECRET_KEY': 'test',
    }
    app = create_app(test_config)
    with app.app_context():
        db.create_all()
    return app


def test_slugify_category_key():
    assert slugify_category_key('Vet Visits') == 'vet_visits'
    assert slugify_category_key('123').startswith('cat_')


def test_normalize_category_list_rejects_duplicates():
    with pytest.raises(ValueError, match='Duplicate'):
        normalize_category_list([
            {'key': 'pets', 'label': 'Pets', 'color': '#111111'},
            {'key': 'pets', 'label': 'Pets 2', 'color': '#222222'},
        ])


def test_save_and_load_categories():
    app = make_app()
    with app.app_context():
        saved = save_reminder_categories([
            {'key': 'pets', 'label': 'Pets', 'color': '#aabbcc'},
            {'key': 'travel', 'label': 'Travel', 'color': '#112233'},
        ])
        assert len(saved) == 2
        loaded = load_reminder_categories(seed_if_empty=False)
        assert loaded[0]['key'] == 'pets'
        assert loaded[1]['color'] == '#112233'


def test_api_list_and_put(client=None):
    app = make_app()
    client = app.test_client()
    r = client.get('/api/reminder-categories')
    assert r.status_code == 200
    data = r.get_json()
    assert data['ok'] is True
    assert len(data['categories']) >= 2

    r2 = client.put(
        '/api/reminder-categories',
        json={
            'categories': [
                {'key': 'school', 'label': 'School', 'color': '#7c3aed'},
                {'key': 'sports', 'label': 'Sports', 'color': '#16a34a'},
            ]
        },
    )
    assert r2.status_code == 200
    cats = r2.get_json()['categories']
    assert cats[1]['key'] == 'sports'

    with app.app_context():
        row = db.session.execute(
            db.text("SELECT value FROM app_setting WHERE key='reminder_categories'")
        ).fetchone()
        assert row is not None
        stored = json.loads(row[0])
        assert stored[0]['label'] == 'School'
