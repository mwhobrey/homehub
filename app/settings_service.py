"""Runtime settings stored in app_setting (admin UI); merged over config.yml on load."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from flask import current_app, has_app_context

from .config import apply_config_defaults, load_config

from .models import db
from .security import sanitize_text

# Keys persisted as JSON in app_setting
_KEY_FEATURE_TOGGLES = 'settings:feature_toggles'
_KEY_WEATHER = 'settings:weather'
_KEY_REMINDERS = 'settings:reminders'
_KEY_INSTANCE_NAME = 'settings:instance_name'
_KEY_NAV_LABELS = 'settings:nav_labels'
# Legacy global theme key (migrated to per-user prefs; no longer merged into hub config).
_KEY_THEME_LEGACY = 'settings:theme'

# Sidebar link keys → default visible labels (title + nav text).
NAV_LABEL_DEFAULTS: dict[str, str] = {
    'welcome': 'Welcome',
    'calendar': 'Calendar',
    'school': 'School',
    'notes': 'Shared Notes',
    'shared_cloud': 'Shared Cloud',
    'shopping_list': 'Shopping List',
    'chores': 'Chores',
    'todo_list': 'To-Do Lists',
    'recipes': 'Recipe Book',
    'expiry_tracker': 'Expiry Tracker',
    'url_shortener': 'URL Shortener',
    'media_downloader': 'Media Downloader',
    'pdf_compressor': 'PDF Compressor',
    'qr_generator': 'QR Generator',
    'expense_tracker': 'Expense Tracker',
    'preferences': 'Preferences',
    'system': 'System',
}

NAV_LABEL_KEYS = tuple(NAV_LABEL_DEFAULTS.keys())

NAV_LABEL_GROUPS = (
    {
        'title': 'Home & planning',
        'description': 'Core household pages in the sidebar.',
        'items': (
            ('welcome', 'Welcome'),
            ('calendar', 'Calendar'),
            ('school', 'School'),
            ('chores', 'Chores'),
            ('todo_list', 'To-Do Lists'),
        ),
    },
    {
        'title': 'Lists & food',
        'items': (
            ('shopping_list', 'Shopping List'),
            ('notes', 'Shared Notes'),
            ('recipes', 'Recipe Book'),
            ('expiry_tracker', 'Expiry Tracker'),
        ),
    },
    {
        'title': 'Tools & files',
        'items': (
            ('shared_cloud', 'Shared Cloud'),
            ('media_downloader', 'Media Downloader'),
            ('pdf_compressor', 'PDF Compressor'),
            ('qr_generator', 'QR Generator'),
            ('url_shortener', 'URL Shortener'),
            ('expense_tracker', 'Expense Tracker'),
        ),
    },
    {
        'title': 'Settings links',
        'description': 'Shown for signed-in users (System is admin-only).',
        'items': (
            ('preferences', 'Preferences'),
            ('system', 'System'),
        ),
    },
)

# Grouped metadata for the settings UI (key must be in FEATURE_TOGGLE_KEYS).
FEATURE_UI_GROUPS = (
    {
        'id': 'home',
        'title': 'Home & dashboard',
        'description': 'Welcome page widgets and household visibility.',
        'features': (
            ('show_chores_on_homepage', 'Chores on home page', 'fa-broom'),
            ('who_is_home', "Who's home", 'fa-house-signal'),
            ('personal_status', 'Personal status', 'fa-user-check'),
        ),
    },
    {
        'id': 'planning',
        'title': 'Planning',
        'description': 'Calendar, school, tasks, and chores.',
        'features': (
            ('calendar', 'Calendar', 'fa-calendar-days'),
            ('school', 'School', 'fa-graduation-cap'),
            ('todo_list', 'To-do lists', 'fa-list-check'),
            ('chores', 'Chores', 'fa-broom'),
        ),
    },
    {
        'id': 'household',
        'title': 'Household',
        'description': 'Shopping, food, and home logistics.',
        'features': (
            ('shopping_list', 'Shopping list', 'fa-cart-shopping'),
            ('recipes', 'Recipes', 'fa-utensils'),
            ('expiry_tracker', 'Expiry tracker', 'fa-hourglass-half'),
        ),
    },
    {
        'id': 'tools',
        'title': 'Tools & sharing',
        'description': 'Utilities and shared content.',
        'features': (
            ('notes', 'Shared notes', 'fa-note-sticky'),
            ('shared_cloud', 'Shared cloud', 'fa-cloud'),
            ('media_downloader', 'Media downloader', 'fa-download'),
            ('pdf_compressor', 'PDF compressor', 'fa-file-pdf'),
            ('qr_generator', 'QR generator', 'fa-qrcode'),
            ('url_shortener', 'URL shortener', 'fa-link'),
        ),
    },
    {
        'id': 'finance',
        'title': 'Finance',
        'description': 'Currency and categories are configured on the Expenses page.',
        'features': (
            ('expense_tracker', 'Expense tracker', 'fa-wallet'),
        ),
    },
)

FEATURE_TOGGLE_KEYS = (
    'shopping_list',
    'media_downloader',
    'pdf_compressor',
    'qr_generator',
    'notes',
    'shared_cloud',
    'who_is_home',
    'personal_status',
    'chores',
    'todo_list',
    'recipes',
    'expiry_tracker',
    'url_shortener',
    'expense_tracker',
    'calendar',
    'school',
    'show_chores_on_homepage',
)

WEATHER_KEYS = ('enabled', 'label', 'latitude', 'longitude', 'timezone', 'units', 'view')
REMINDER_UI_KEYS = ('time_format', 'calendar_start_day', 'default_timezone')
THEME_KEYS = (
    'primary_color',
    'secondary_color',
    'background_color',
    'card_background_color',
    'text_color',
    'sidebar_background_color',
    'sidebar_text_color',
    'sidebar_link_color',
    'sidebar_link_border_color',
    'sidebar_active_color',
)


def _ensure_app_setting_table() -> None:
    db.session.execute(db.text('CREATE TABLE IF NOT EXISTS app_setting (key TEXT PRIMARY KEY, value TEXT)'))
    db.session.commit()


def _get_setting(key: str) -> str | None:
    if not has_app_context():
        return None
    try:
        _ensure_app_setting_table()
        row = db.session.execute(
            db.text('SELECT value FROM app_setting WHERE key=:k'),
            {'k': key},
        )
        val = row.scalar()
        return val if val is not None else None
    except Exception:
        return None


def _set_setting(key: str, value: str) -> None:
    _ensure_app_setting_table()
    db.session.execute(
        db.text(
            'INSERT INTO app_setting(key, value) VALUES(:k, :v) '
            'ON CONFLICT(key) DO UPDATE SET value=excluded.value'
        ),
        {'k': key, 'v': value},
    )
    db.session.commit()


def _load_json_setting(key: str) -> dict | None:
    raw = _get_setting(key)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (TypeError, ValueError):
        return None


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = deepcopy(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def reload_merged_config() -> dict:
    """Reload config.yml (or in-memory test config) and apply DB overrides."""
    if current_app.config.get('TESTING'):
        base = apply_config_defaults(dict(current_app.config.get('HOMEHUB_CONFIG') or {}))
    else:
        base = load_config()
    return merge_runtime_settings(base)


def merge_runtime_settings(config: dict) -> dict:
    """Apply DB overrides on top of config.yml (no secrets loaded from DB)."""
    if not has_app_context():
        return config
    cfg = deepcopy(config)
    toggles = _load_json_setting(_KEY_FEATURE_TOGGLES)
    if toggles:
        ft = dict(cfg.get('feature_toggles') or {})
        for key in FEATURE_TOGGLE_KEYS:
            if key in toggles:
                ft[key] = bool(toggles[key])
        cfg['feature_toggles'] = ft
    # Legacy single-key override for homepage chores widget
    chores_home = _get_setting('show_chores_on_homepage')
    if chores_home is not None:
        ft = dict(cfg.get('feature_toggles') or {})
        ft['show_chores_on_homepage'] = str(chores_home).strip().lower() in ('1', 'true', 'yes', 'on')
        cfg['feature_toggles'] = ft
    weather = _load_json_setting(_KEY_WEATHER)
    if weather:
        cfg['weather'] = _deep_merge(cfg.get('weather') or {}, weather)
    reminders = _load_json_setting(_KEY_REMINDERS)
    if reminders:
        cfg['reminders'] = _deep_merge(cfg.get('reminders') or {}, reminders)
    instance = _get_setting(_KEY_INSTANCE_NAME)
    if instance:
        cfg['instance_name'] = instance
    nav_db = _load_json_setting(_KEY_NAV_LABELS)
    if nav_db:
        merged_nav = dict(cfg.get('nav_labels') or {})
        for key in NAV_LABEL_KEYS:
            if key in nav_db and nav_db[key]:
                merged_nav[key] = str(nav_db[key])[:80]
        cfg['nav_labels'] = merged_nav
    return cfg


def resolve_nav_label(config: dict, key: str) -> str:
    """Display label for a sidebar nav item (custom override or default)."""
    default = NAV_LABEL_DEFAULTS.get(key, key.replace('_', ' ').title())
    overrides = config.get('nav_labels') or {}
    custom = overrides.get(key)
    if custom is not None and str(custom).strip():
        return str(custom).strip()[:80]
    return default


def build_nav_label_groups_for_ui(config: dict) -> list[dict]:
    overrides = config.get('nav_labels') or {}
    groups = []
    for spec in NAV_LABEL_GROUPS:
        items = []
        for key, default_label in spec['items']:
            items.append({
                'key': key,
                'default': default_label,
                'value': overrides.get(key, '') or '',
            })
        groups.append({
            'title': spec['title'],
            'description': spec.get('description', ''),
            'items': items,
        })
    return groups


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def build_feature_groups_for_ui(feature_toggles: dict[str, bool]) -> list[dict]:
    """Feature toggles grouped for the settings page."""
    assigned: set[str] = set()
    groups: list[dict] = []
    for spec in FEATURE_UI_GROUPS:
        items = []
        for key, label, icon in spec['features']:
            if key not in feature_toggles:
                continue
            assigned.add(key)
            items.append({
                'key': key,
                'label': label,
                'icon': icon,
                'enabled': feature_toggles[key],
            })
        if items:
            groups.append({
                'id': spec['id'],
                'title': spec['title'],
                'description': spec['description'],
                'items': items,
            })
    other = [
        {
            'key': key,
            'label': key.replace('_', ' ').title(),
            'icon': 'fa-puzzle-piece',
            'enabled': feature_toggles[key],
        }
        for key in FEATURE_TOGGLE_KEYS
        if key in feature_toggles and key not in assigned
    ]
    if other:
        groups.append({
            'id': 'other',
            'title': 'Other',
            'description': 'Additional toggles from config.',
            'items': other,
        })
    return groups


def build_settings_form_context(config: dict) -> dict:
    """Safe snapshot for the settings template (no auth secrets)."""
    ft = config.get('feature_toggles') or {}
    weather = config.get('weather') or {}
    reminders = config.get('reminders') or {}
    feature_toggles = {
        k: _coerce_bool(ft.get(k, False if k == 'show_chores_on_homepage' else True))
        for k in FEATURE_TOGGLE_KEYS
    }
    return {
        'instance_name': config.get('instance_name', 'HomeHub'),
        'feature_toggles': feature_toggles,
        'feature_groups': build_feature_groups_for_ui(feature_toggles),
        'weather': {k: weather.get(k, '') for k in WEATHER_KEYS},
        'reminders': {
            'time_format': reminders.get('time_format') or '12h',
            'calendar_start_day': reminders.get('calendar_start_day') or 'sunday',
            'default_timezone': reminders.get('default_timezone') or '',
        },
        'nav_label_groups': build_nav_label_groups_for_ui(config),
        'has_db_overrides': any(
            _get_setting(k) for k in (
                _KEY_FEATURE_TOGGLES,
                _KEY_WEATHER,
                _KEY_REMINDERS,
                _KEY_INSTANCE_NAME,
                _KEY_NAV_LABELS,
                'show_chores_on_homepage',
            )
        ),
    }


def save_settings_from_form(form, *, base_config: dict | None = None) -> None:
    """Persist admin form values to app_setting."""
    base = base_config or {}
    toggles = {}
    for key in FEATURE_TOGGLE_KEYS:
        toggles[key] = _coerce_bool(form.get(f'toggle_{key}'))
    _set_setting(_KEY_FEATURE_TOGGLES, json.dumps(toggles))
    # Keep dashboard/chores helpers in sync
    _set_setting(
        'show_chores_on_homepage',
        '1' if toggles.get('show_chores_on_homepage') else '0',
    )
    instance = sanitize_text(form.get('instance_name', ''))[:120]
    if instance:
        _set_setting(_KEY_INSTANCE_NAME, instance)
    weather = {}
    for key in WEATHER_KEYS:
        if key == 'enabled':
            weather[key] = _coerce_bool(form.get('weather_enabled'))
        else:
            weather[key] = sanitize_text(form.get(f'weather_{key}', ''))[:200]
    if weather.get('units') not in ('metric', 'imperial', ''):
        weather['units'] = 'metric'
    if weather.get('view') not in ('compact', 'detailed', ''):
        weather['view'] = 'compact'
    _set_setting(_KEY_WEATHER, json.dumps(weather))
    reminders = {
        'time_format': sanitize_text(form.get('reminder_time_format', '12h'))[:8],
        'calendar_start_day': sanitize_text(form.get('reminder_calendar_start_day', 'sunday'))[:16],
        'default_timezone': sanitize_text(form.get('reminder_default_timezone', ''))[:64],
    }
    if reminders['time_format'] not in ('12h', '24h'):
        reminders['time_format'] = '12h'
    _set_setting(_KEY_REMINDERS, json.dumps(reminders))
    nav_stored: dict[str, str] = {}
    for key in NAV_LABEL_KEYS:
        raw = sanitize_text(form.get(f'nav_label_{key}', ''))[:80]
        default = NAV_LABEL_DEFAULTS[key]
        if raw and raw != default:
            nav_stored[key] = raw
    _set_setting(_KEY_NAV_LABELS, json.dumps(nav_stored))


def clear_runtime_overrides() -> None:
    """Remove UI overrides; config.yml values take effect again."""
    keys = (
        _KEY_FEATURE_TOGGLES,
        _KEY_WEATHER,
        _KEY_REMINDERS,
        _KEY_THEME_LEGACY,
        _KEY_INSTANCE_NAME,
        _KEY_NAV_LABELS,
        'show_chores_on_homepage',
    )
    _ensure_app_setting_table()
    for key in keys:
        db.session.execute(db.text('DELETE FROM app_setting WHERE key=:k'), {'k': key})
    db.session.commit()
    left = db.session.execute(
        db.text("SELECT COUNT(*) FROM app_setting WHERE key LIKE 'settings:%' OR key = 'show_chores_on_homepage'")
    ).scalar()
    if left:
        raise RuntimeError(f'Failed to clear {left} app_setting override row(s)')
