import yaml
import os
import hashlib

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.yml')

def apply_config_defaults(config: dict) -> dict:
    """Fill missing keys so templates and routes always have expected structure."""
    config = dict(config or {})
    if 'password' in config and config['password']:
        config['password_hash'] = hashlib.sha256(config['password'].encode()).hexdigest()
        del config['password']
    # Ensure feature_toggles exists
    config.setdefault('feature_toggles', {})
    # Ensure Who is Home widget is enabled by default unless explicitly disabled in config.yml
    config['feature_toggles'].setdefault('who_is_home', True)
    # Personal status feature toggle (new)
    config['feature_toggles'].setdefault('personal_status', True)
    # Homepage chores widget toggle (runtime value may be overridden in app_setting)
    config['feature_toggles'].setdefault('show_chores_on_homepage', False)
    config['feature_toggles'].setdefault('calendar', True)
    config['feature_toggles'].setdefault('school', True)
    school = config.setdefault('school', {})
    school.setdefault('teachers', [])
    school.setdefault('students', [])
    school.setdefault('parent_observers', {})
    # Reminders defaults & calendar start day (supports sunday..saturday or 0-6)
    rem = config.setdefault('reminders', {})
    # Do not overwrite existing user value
    if 'calendar_start_day' not in rem or rem.get('calendar_start_day') in (None, ''):
        rem.setdefault('calendar_start_day', 'sunday')  # default Sunday to align with expense tracker
    # Admin name default (legacy auth)
    config.setdefault('admin_name', 'Administrator')
    # Family members default list (legacy UI picker)
    config.setdefault('family_members', [])
    # Auth block: mode legacy | firebase
    auth = config.setdefault('auth', {})
    auth.setdefault('mode', 'legacy')
    fb = auth.setdefault('firebase', {})
    fb.setdefault('api_key', '')
    fb.setdefault('auth_domain', '')
    fb.setdefault('project_id', '')
    fb.setdefault('app_id', '')
    auth.setdefault('allowed_emails', [])
    auth.setdefault('admin_emails', [])
    auth.setdefault('display_names', {})  # email -> friendly name for creator fields
    # Theme defaults
    theme = config.setdefault('theme', {})
    theme.setdefault('primary_color', '#1d4ed8')
    theme.setdefault('secondary_color', '#a0aec0')
    theme.setdefault('background_color', '#f7fafc')
    theme.setdefault('card_background_color', '#ffffff')
    theme.setdefault('text_color', '#333333')
    theme.setdefault('sidebar_background_color', '#2563eb')
    theme.setdefault('sidebar_text_color', '#ffffff')
    theme.setdefault('sidebar_link_color', 'rgba(255,255,255,0.95)')
    theme.setdefault('sidebar_link_border_color', 'rgba(255,255,255,0.18)')
    # Weather widget defaults
    weather = config.setdefault('weather', {})
    weather.setdefault('enabled', False)
    weather.setdefault('label', '')
    weather.setdefault('latitude', '')
    weather.setdefault('longitude', '')
    weather.setdefault('timezone', '')
    weather.setdefault('units', 'metric')
    weather.setdefault('view', 'compact')
    theme.setdefault('sidebar_active_color', theme.get('sidebar_active_color', '#3b82f6'))
    # Feature hardening (public-internet defaults lean secure)
    hard = config.setdefault('hardening', {})
    media = hard.setdefault('media_downloader', {})
    media.setdefault('allowed_domains', [
        'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com',
        'youtu.be', 'vimeo.com', 'www.vimeo.com',
    ])
    media.setdefault('max_filesize_mb', 500)
    media.setdefault('max_concurrent_per_user', 2)
    media.setdefault('download_timeout_minutes', 45)
    media.setdefault('admin_only', False)
    media.setdefault('rate_limit', '8 per hour')
    qr = hard.setdefault('qr_generator', {})
    qr.setdefault('max_payload_length', 2048)
    qr.setdefault('store_wifi_history', False)
    qr.setdefault('history_retention_days', 7)
    qr.setdefault('encrypt_payloads', True)
    qr.setdefault('admin_only_wifi', False)
    gcal = config.setdefault('google_calendar', {})
    gcal.setdefault('enabled', False)
    gcal.setdefault('client_id', os.environ.get('GOOGLE_CALENDAR_CLIENT_ID', ''))
    secret = gcal.get('client_secret') or os.environ.get('GOOGLE_CALENDAR_CLIENT_SECRET', '')
    gcal['client_secret'] = secret
    gcal.setdefault('sync_interval_minutes', 15)
    gcal.setdefault('default_timezone', 'America/Chicago')
    gcal.setdefault('onboarding_all_calendars_enabled', True)
    legal = config.setdefault('legal', {})
    legal.setdefault('contact_email', '')
    legal.setdefault('policy_updated', '2026-06-01')
    return config


def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f'config.yml not found at {CONFIG_PATH}.')
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}
    return apply_config_defaults(config)
