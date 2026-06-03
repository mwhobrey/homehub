import json



import pytest



from app import create_app, db

from app.settings_service import merge_runtime_settings, resolve_nav_label, save_settings_from_form

from app.user_preferences_service import (

    clear_user_preferences,

    load_user_preferences,

    save_user_preferences_from_form,

)





def make_app():

    test_config = {

        'TESTING': True,

        'SQLALCHEMY_DATABASE_URI': 'sqlite://',

        'HOMEHUB_CONFIG': {

            'admin_name': 'Administrator',

            'instance_name': 'Test Hub',

            'feature_toggles': {

                'notes': True,

                'shopping_list': True,

                'show_chores_on_homepage': False,

            },

            'weather': {'enabled': False, 'units': 'metric'},

            'reminders': {'time_format': '12h', 'calendar_start_day': 'sunday'},

            'theme': {'primary_color': '#111111', 'background_color': '#eeeeee'},

        },

        'WTF_CSRF_ENABLED': False,

        'SECRET_KEY': 'test',

    }

    app = create_app(test_config)

    with app.app_context():

        db.create_all()

    return app





@pytest.fixture()

def client():

    return make_app().test_client()





def test_system_settings_requires_admin(client):

    resp = client.get('/settings/system')

    assert resp.status_code == 302





def test_system_settings_admin_legacy(client):

    client.post('/notes', data={'content': 'x', 'creator': 'Administrator'}, follow_redirects=True)

    resp = client.get('/settings/system?user=Administrator')

    assert resp.status_code == 200

    assert b'System settings</h1>' in resp.data





def test_user_preferences_open_legacy(client):

    client.post('/notes', data={'content': 'x', 'creator': 'Alice'}, follow_redirects=True)

    resp = client.get('/settings?user=Alice')

    assert resp.status_code == 200

    assert b'Your preferences</h1>' in resp.data





def test_save_feature_toggle_persists(client):

    client.post('/notes', data={'content': 'x', 'creator': 'Administrator'}, follow_redirects=True)

    resp = client.post(

        '/settings/system',

        data={

            'user': 'Administrator',

            'instance_name': 'Renamed Hub',

            'toggle_notes': '1',

            'toggle_shopping_list': '',

            'weather_enabled': '',

            'reminder_time_format': '24h',

            'reminder_calendar_start_day': 'monday',

        },

        follow_redirects=True,

    )

    assert resp.status_code == 200

    assert b'System settings saved' in resp.data or b'Renamed Hub' in resp.data

    with client.application.app_context():

        row = db.session.execute(

            db.text("SELECT value FROM app_setting WHERE key='settings:feature_toggles'")

        ).scalar()

        data = json.loads(row)

        assert data['shopping_list'] is False

        cfg = merge_runtime_settings(client.application.config['HOMEHUB_CONFIG'])

        assert cfg['instance_name'] == 'Renamed Hub'

        assert cfg['feature_toggles']['shopping_list'] is False

        assert cfg['reminders']['time_format'] == '24h'





def test_user_color_mode_isolated(client):

    client.post('/notes', data={'content': 'x', 'creator': 'Administrator'}, follow_redirects=True)

    client.post('/notes', data={'content': 'y', 'creator': 'Alice'}, follow_redirects=True)

    client.post(

        '/settings',

        data={'user': 'Administrator', 'color_mode': 'light'},

        follow_redirects=True,

    )

    client.post(

        '/settings',

        data={'user': 'Alice', 'color_mode': 'dark'},

        follow_redirects=True,

    )

    with client.application.app_context():

        admin_prefs = load_user_preferences(actor='Administrator')

        alice_prefs = load_user_preferences(actor='Alice')

        assert admin_prefs['color_mode'] == 'light'

        assert alice_prefs['color_mode'] == 'dark'





def test_system_save_does_not_set_global_theme(client):

    client.post('/notes', data={'content': 'x', 'creator': 'Administrator'}, follow_redirects=True)

    client.post(

        '/settings/system',

        data={

            'user': 'Administrator',

            'instance_name': 'Hub',

            'toggle_notes': '1',

            'theme_primary_color': '#ff0000',

        },

        follow_redirects=True,

    )

    with client.application.app_context():

        row = db.session.execute(

            db.text("SELECT value FROM app_setting WHERE key='settings:theme'")

        ).scalar()

        assert row is None





def test_settings_reset_clears_overrides(client):

    client.post('/notes', data={'content': 'x', 'creator': 'Administrator'}, follow_redirects=True)

    client.post(

        '/settings/system',

        data={'user': 'Administrator', 'instance_name': 'Temp', 'toggle_notes': '1'},

        follow_redirects=True,

    )

    reset = client.post('/settings/reset', data={'user': 'Administrator'}, follow_redirects=False)

    assert reset.status_code == 302

    assert '/settings/system' in (reset.location or '')

    with client.application.app_context():

        db.session.expire_all()

        row = db.session.execute(

            db.text("SELECT value FROM app_setting WHERE key='settings:instance_name'")

        ).scalar()

        assert row is None





def test_clear_overrides_direct(client):

    with client.application.app_context():

        from app.settings_service import _set_setting, clear_runtime_overrides



        _set_setting('settings:instance_name', 'X')

        clear_runtime_overrides()

        row = db.session.execute(

            db.text("SELECT value FROM app_setting WHERE key='settings:instance_name'")

        ).scalar()

        assert row is None





def test_non_admin_cannot_save_system(client):

    client.post('/notes', data={'content': 'x', 'creator': 'Alice'}, follow_redirects=True)

    resp = client.post(

        '/settings/system',

        data={'user': 'Alice', 'instance_name': 'Hacked'},

        follow_redirects=False,

    )

    assert resp.status_code == 302

    assert 'settings/system' not in (resp.location or '')





def test_non_admin_can_save_user_prefs(client):

    client.post('/notes', data={'content': 'x', 'creator': 'Alice'}, follow_redirects=True)

    resp = client.post(

        '/settings',

        data={'user': 'Alice', 'color_mode': 'dark'},

        follow_redirects=True,

    )

    assert resp.status_code == 200

    assert b'preferences were saved' in resp.data.lower() or b'saved' in resp.data.lower()





def test_nav_label_override(client):
    client.post('/notes', data={'content': 'x', 'creator': 'Administrator'}, follow_redirects=True)
    client.post(
        '/settings/system',
        data={
            'user': 'Administrator',
            'instance_name': 'Test Hub',
            'toggle_notes': '1',
            'toggle_chores': '1',
            'nav_label_chores': 'Honey-Do List',
        },
        follow_redirects=True,
    )
    with client.application.app_context():
        cfg = merge_runtime_settings(client.application.config['HOMEHUB_CONFIG'])
        assert resolve_nav_label(cfg, 'chores') == 'Honey-Do List'
        assert resolve_nav_label(cfg, 'calendar') == 'Calendar'
    resp = client.get('/?user=Administrator')
    assert b'Honey-Do List' in resp.data


def test_user_preferences_service_save(client):

    with client.application.app_context():

        save_user_preferences_from_form(

            {'user': 'Bob', 'color_mode': 'light', 'theme_primary_color': '#222222'},

            base_config=client.application.config['HOMEHUB_CONFIG'],

        )

        prefs = load_user_preferences(actor='Bob')

        assert prefs['color_mode'] == 'light'

        assert prefs['theme'].get('primary_color') == '#222222'

        clear_user_preferences(actor='Bob')


