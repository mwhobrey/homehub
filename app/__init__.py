from flask import Flask, request, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.middleware.proxy_fix import ProxyFix
from .config import load_config, apply_config_defaults
from .extensions import limiter
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

db = SQLAlchemy()

_calendar_scheduler_started = False
_calendar_sync_timer = None

_DEV_SECRET_FILE = '.secret_key'


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def _resolve_secret_key(base_dir: str, *, testing: bool) -> str:
    """Stable key for local dev; env SECRET_KEY for production."""
    env_secret = (os.environ.get('SECRET_KEY') or '').strip()
    if env_secret:
        return env_secret
    if testing:
        return 'test'
    is_prod = os.environ.get('FLASK_ENV') == 'production'
    if not is_prod:
        path = os.path.join(base_dir, 'data', _DEV_SECRET_FILE)
        try:
            if os.path.isfile(path):
                with open(path, encoding='utf-8') as fh:
                    stored = fh.read().strip()
                if stored:
                    return stored
        except OSError:
            pass
        import secrets as _secrets

        generated = _secrets.token_hex(32)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(generated + '\n')
        except OSError:
            pass
        return generated
    import secrets as _secrets

    return _secrets.token_hex(32)


_ASSET_BUST_FILES = (
    'output.css',
    'input.css',
    'js/calendar_sync.js',
    'js/calendar_app.js',
)


def resolve_asset_version(app: Flask) -> str:
    """Cache-bust static assets in dev; use SW_CACHE_VERSION in production images."""
    env_v = (os.environ.get('SW_CACHE_VERSION') or '').strip()
    if env_v and env_v not in ('dev', 'development'):
        return env_v
    static_root = Path(app.static_folder) if app.static_folder else Path('static')
    if not static_root.is_absolute():
        static_root = Path(app.root_path) / static_root
    stamps: list[int] = []
    for rel in _ASSET_BUST_FILES:
        path = static_root / rel
        try:
            if path.is_file():
                stamps.append(int(path.stat().st_mtime))
        except OSError:
            continue
    if stamps:
        return str(max(stamps))
    return env_v or 'dev'


def _should_run_background_jobs(app) -> bool:
    """Avoid starting timers in the Werkzeug reloader parent (duplicate sync + Win socket bugs)."""
    if os.environ.get('HOMEHUB_DISABLE_BACKGROUND_JOBS', '').lower() in ('1', 'true', 'yes'):
        return False
    if app.config.get('TESTING'):
        return False
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        return True
    if not app.debug:
        return True
    use_reloader = os.environ.get('FLASK_USE_RELOADER', 'auto').lower()
    if use_reloader in ('0', 'false', 'no'):
        return True
    if use_reloader == 'auto' and os.name == 'nt':
        return True
    return False


def stop_background_jobs() -> None:
    """Cancel pending calendar sync timers so Ctrl+C can exit promptly."""
    global _calendar_scheduler_started, _calendar_sync_timer
    if _calendar_sync_timer is not None:
        _calendar_sync_timer.cancel()
        _calendar_sync_timer = None
    _calendar_scheduler_started = False


def _start_calendar_sync_scheduler(app):
    global _calendar_scheduler_started, _calendar_sync_timer
    if _calendar_scheduler_started:
        return
    cfg = (app.config.get('HOMEHUB_CONFIG') or {}).get('google_calendar') or {}
    if not cfg.get('enabled'):
        return
    interval = int(cfg.get('sync_interval_minutes') or 15)
    if interval < 1:
        interval = 15

    import threading

    def _schedule(delay_sec: float) -> None:
        global _calendar_sync_timer
        stop_background_jobs()
        _calendar_scheduler_started = True
        timer = threading.Timer(delay_sec, _tick)
        timer.daemon = True
        _calendar_sync_timer = timer
        timer.start()

    def _tick():
        with app.app_context():
            try:
                from .google_calendar.sync import sync_all_connections
                sync_all_connections()
            except Exception:
                app.logger.exception('calendar sync scheduler tick failed')
        _schedule(interval * 60)

    _schedule(30)


def create_app(test_config: dict | None = None):
    _load_dotenv()
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    templates_dir = os.path.join(base_dir, 'templates')
    static_dir = os.path.join(base_dir, 'static')

    app = Flask(
        __name__,
        template_folder=templates_dir,
        static_folder=static_dir,
    )

    # Paths
    data_dir = os.path.join(base_dir, 'data')
    uploads_dir = os.path.join(base_dir, 'uploads')
    media_dir = os.path.join(base_dir, 'media')
    pdfs_dir = os.path.join(base_dir, 'pdfs')
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(uploads_dir, exist_ok=True)
    os.makedirs(media_dir, exist_ok=True)
    os.makedirs(pdfs_dir, exist_ok=True)

    # SQLite DB file at an absolute path to avoid driver path issues
    db_path = os.path.join(base_dir, 'data', 'app.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = _resolve_secret_key(base_dir, testing=bool(test_config))
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    behind_proxy = os.environ.get('TRUST_PROXY', '1') == '1'
    app.config['SESSION_COOKIE_SECURE'] = (
        os.environ.get('SESSION_COOKIE_SECURE', '1' if behind_proxy else '0') == '1'
    )
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(
        days=int(os.environ.get('SESSION_DAYS', '14'))
    )
    max_mb = int(os.environ.get('MAX_UPLOAD_MB', '50'))
    app.config['MAX_CONTENT_LENGTH'] = max_mb * 1024 * 1024

    # Allow tests to override configuration before loading config.yml
    if test_config:
        app.config.update(test_config)

    if 'HOMEHUB_CONFIG' not in app.config:
        app.config['HOMEHUB_CONFIG'] = load_config()
    else:
        app.config['HOMEHUB_CONFIG'] = apply_config_defaults(app.config['HOMEHUB_CONFIG'])

    db.init_app(app)
    limiter.init_app(app)

    if behind_proxy:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    @app.after_request
    def set_security_headers(response):
        if request.endpoint and str(request.endpoint).startswith('static'):
            return response
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        if app.config.get('SESSION_COOKIE_SECURE'):
            response.headers.setdefault(
                'Strict-Transport-Security',
                'max-age=31536000; includeSubDomains',
            )
        return response

    # Ensure models are imported before creating tables
    with app.app_context():
        from . import models  # noqa: F401 ensures model metadata is registered
        db.create_all()
        try:
            from .google_calendar.imports import ensure_household_calendar
            ensure_household_calendar()
            db.session.commit()
        except Exception:
            db.session.rollback()
        # Perform tiny auto-migrations for SQLite to add missing columns if upgrading
        # Skip this block in testing to avoid touching the real DB path
        if not app.config.get('TESTING'):
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                # Import models to get actual table names
                from .models import (
                    RecurringExpense as _RecurringExpense,
                    QRCode as _QRCode,
                    Reminder as _Reminder,
                )  # noqa: F401
                # Helper to check column existence
                def has_column(table, column):
                    cur.execute(f"PRAGMA table_info({table})")
                    return any(row[1] == column for row in cur.fetchall())
                # Add 'done' to chore
                if not has_column('chore', 'done'):
                    cur.execute("ALTER TABLE chore ADD COLUMN done INTEGER DEFAULT 0")
                if not has_column('chore', 'due_date'):
                    cur.execute("ALTER TABLE chore ADD COLUMN due_date DATE")
                if not has_column('chore', 'recurring_id'):
                    cur.execute("ALTER TABLE chore ADD COLUMN recurring_id INTEGER")
                # Add 'tags' to shoppingitem and chore for multi-tag feature
                if not has_column('shopping_item', 'tags'):
                    cur.execute("ALTER TABLE shopping_item ADD COLUMN tags TEXT DEFAULT '[]'")
                if not has_column('chore', 'tags'):
                    cur.execute("ALTER TABLE chore ADD COLUMN tags TEXT DEFAULT '[]'")
                # Add 'status' to media
                if not has_column('media', 'status'):
                    cur.execute("ALTER TABLE media ADD COLUMN status TEXT DEFAULT 'done'")
                # Add 'progress' to media
                if not has_column('media', 'progress'):
                    cur.execute("ALTER TABLE media ADD COLUMN progress TEXT")
                # Reminder new columns (category, color, updated_at)
                if not has_column('reminder', 'category'):
                    cur.execute("ALTER TABLE reminder ADD COLUMN category TEXT")
                if not has_column('reminder', 'color'):
                    cur.execute("ALTER TABLE reminder ADD COLUMN color TEXT")
                if not has_column('reminder', 'updated_at'):
                    cur.execute("ALTER TABLE reminder ADD COLUMN updated_at TIMESTAMP")
                if not has_column('reminder', 'time'):
                    cur.execute("ALTER TABLE reminder ADD COLUMN time TEXT")
                # Ensure memberstatus table exists
                cur.execute("CREATE TABLE IF NOT EXISTS member_status (id INTEGER PRIMARY KEY, name TEXT, text TEXT, updated_at TIMESTAMP)")
                # Ensure new tables for groceries and expenses exist
                cur.execute("CREATE TABLE IF NOT EXISTS grocery_history (id INTEGER PRIMARY KEY, item TEXT, creator TEXT, timestamp TIMESTAMP)")
                cur.execute("CREATE TABLE IF NOT EXISTS recurring_expense (id INTEGER PRIMARY KEY, title TEXT, unit_price REAL, default_quantity REAL, frequency TEXT, start_date DATE, end_date DATE, last_generated_date DATE, creator TEXT, timestamp TIMESTAMP)")
                cur.execute("CREATE TABLE IF NOT EXISTS expense_entry (id INTEGER PRIMARY KEY, date DATE, title TEXT, category TEXT, unit_price REAL, quantity REAL, amount REAL, payer TEXT, recurring_id INTEGER, timestamp TIMESTAMP)")
                # Add monthly_mode to recurring_expense if missing
                def ensure_column(table, col, type_spec, default=None):
                    cur.execute(f"PRAGMA table_info({table})")
                    cols = [row[1] for row in cur.fetchall()]
                    if col not in cols:
                        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {type_spec}")
                        if default is not None:
                            cur.execute(f"UPDATE {table} SET {col}=? WHERE {col} IS NULL", (default,))
                ensure_column(_RecurringExpense.__tablename__, 'monthly_mode', 'TEXT', 'day_of_month')
                ensure_column(_RecurringExpense.__tablename__, 'category', 'TEXT', None)
                ensure_column(_RecurringExpense.__tablename__, 'effective_from', 'DATE', None)
                # Basic settings table (key/value) for currency and categories
                cur.execute("CREATE TABLE IF NOT EXISTS app_setting (key TEXT PRIMARY KEY, value TEXT)")
                # New columns for QRCode and Reminder
                ensure_column(_QRCode.__tablename__, 'original_input', 'TEXT', None)
                ensure_column(_QRCode.__tablename__, 'display_label', 'TEXT', None)
                ensure_column(_QRCode.__tablename__, 'is_wifi', 'INTEGER', 0)
                ensure_column(_Reminder.__tablename__, 'recurring_id', 'INTEGER', None)
                ensure_column(_Reminder.__tablename__, 'source', 'TEXT', 'local')
                ensure_column(_Reminder.__tablename__, 'linked_calendar_id', 'INTEGER', None)
                ensure_column(_Reminder.__tablename__, 'google_event_id', 'TEXT', None)
                ensure_column(_Reminder.__tablename__, 'google_recurring_event_id', 'TEXT', None)
                ensure_column(_Reminder.__tablename__, 'google_etag', 'TEXT', None)
                ensure_column(_Reminder.__tablename__, 'google_updated', 'TEXT', None)
                ensure_column(_Reminder.__tablename__, 'owner_uid', 'TEXT', None)
                ensure_column(_Reminder.__tablename__, 'sync_status', 'TEXT', 'synced')
                ensure_column(_Reminder.__tablename__, 'all_day', 'INTEGER', 0)
                ensure_column(_Reminder.__tablename__, 'end_date', 'DATE', None)
                ensure_column(_Reminder.__tablename__, 'end_time', 'TEXT', None)
                ensure_column(_Reminder.__tablename__, 'time_zone', 'TEXT', None)
                ensure_column(_Reminder.__tablename__, 'attendees_json', 'TEXT', None)
                ensure_column(_Reminder.__tablename__, 'personal_calendar_id', 'INTEGER', None)
                ensure_column('recurring_reminder', 'exception_dates_json', 'TEXT', None)
                ensure_column('recurring_reminder', 'linked_calendar_id', 'INTEGER', None)
                ensure_column('recurring_reminder', 'google_recurring_event_id', 'TEXT', None)
                ensure_column('recurring_reminder', 'google_etag', 'TEXT', None)
                ensure_column('recurring_reminder', 'owner_uid', 'TEXT', None)
                ensure_column('recurring_reminder', 'source', 'TEXT', 'local')
                ensure_column('recurring_reminder', 'sync_status', 'TEXT', 'synced')
                ensure_column('recurring_reminder', 'personal_calendar_id', 'INTEGER', None)
                ensure_column('calendar_connection', 'sync_mode', 'TEXT', 'import_only')
                # Add 'tags' to recipe for multi-tag feature
                if not has_column('recipe', 'tags'):
                    cur.execute("ALTER TABLE recipe ADD COLUMN tags TEXT DEFAULT '[]'")
                # Ensure recurring_reminder table exists (if not created by SQLAlchemy create_all)
                cur.execute("""
                CREATE TABLE IF NOT EXISTS recurring_reminder (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    creator TEXT,
                    frequency TEXT,
                    monthly_mode TEXT,
                    interval INTEGER,
                    unit TEXT,
                    time TEXT,
                    category TEXT,
                    color TEXT,
                    start_date DATE,
                    end_date DATE,
                    last_generated_date DATE,
                    effective_from DATE,
                    timestamp TIMESTAMP
                )
                """)
                # Ensure recurring_chore table exists
                cur.execute("""
                CREATE TABLE IF NOT EXISTS recurring_chore (
                    id INTEGER PRIMARY KEY,
                    description TEXT NOT NULL,
                    creator TEXT,
                    tags TEXT,
                    interval INTEGER,
                    unit TEXT,
                    start_date DATE,
                    end_date DATE,
                    last_generated_date DATE,
                    timestamp TIMESTAMP
                )
                """)
                # Add new interval/unit columns if missing and backfill defaults
                ensure_column('recurring_reminder', 'interval', 'INTEGER', 1)
                ensure_column('recurring_reminder', 'unit', 'TEXT', 'day')
                cur.execute("""
                CREATE TABLE IF NOT EXISTS personal_calendar (
                    id INTEGER PRIMARY KEY,
                    owner_uid TEXT NOT NULL,
                    name TEXT NOT NULL,
                    color TEXT,
                    visibility TEXT DEFAULT 'private',
                    archived INTEGER DEFAULT 0,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS ix_personal_calendar_owner_uid ON personal_calendar(owner_uid)")
                cur.execute("""
                CREATE TABLE IF NOT EXISTS personal_calendar_share (
                    id INTEGER PRIMARY KEY,
                    personal_calendar_id INTEGER NOT NULL,
                    grantee_uid TEXT NOT NULL,
                    can_write INTEGER DEFAULT 0,
                    UNIQUE(personal_calendar_id, grantee_uid)
                )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS ix_personal_calendar_share_personal_calendar_id ON personal_calendar_share(personal_calendar_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS ix_personal_calendar_share_grantee_uid ON personal_calendar_share(grantee_uid)")
                cur.execute(
                    "SELECT id FROM personal_calendar WHERE owner_uid=? AND visibility='household' AND archived=0 LIMIT 1",
                    ('__household__',),
                )
                household_row = cur.fetchone()
                if household_row:
                    household_id = household_row[0]
                else:
                    cur.execute(
                        "INSERT INTO personal_calendar(owner_uid, name, color, visibility, archived, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                        ('__household__', 'Household', '#2563eb', 'household', 0, now, now),
                    )
                    household_id = cur.lastrowid
                cur.execute(
                    "UPDATE reminder SET personal_calendar_id=? WHERE personal_calendar_id IS NULL",
                    (household_id,),
                )
                cur.execute(
                    "UPDATE recurring_reminder SET personal_calendar_id=? WHERE personal_calendar_id IS NULL",
                    (household_id,),
                )
                cur.execute("""
                CREATE TABLE IF NOT EXISTS calendar_import_profile (
                    id INTEGER PRIMARY KEY,
                    connection_id INTEGER NOT NULL UNIQUE,
                    default_sync_mode TEXT DEFAULT 'import_only',
                    require_mapping_review INTEGER DEFAULT 1,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
                """)
                cur.execute("""
                CREATE TABLE IF NOT EXISTS calendar_import_mapping (
                    id INTEGER PRIMARY KEY,
                    connection_id INTEGER NOT NULL,
                    linked_calendar_id INTEGER NOT NULL,
                    personal_calendar_id INTEGER NOT NULL,
                    import_enabled INTEGER DEFAULT 1,
                    import_color TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS ix_calendar_import_mapping_connection_id ON calendar_import_mapping(connection_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS ix_calendar_import_mapping_linked_calendar_id ON calendar_import_mapping(linked_calendar_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS ix_calendar_import_mapping_personal_calendar_id ON calendar_import_mapping(personal_calendar_id)")
                cur.execute("""
                CREATE TABLE IF NOT EXISTS category_import_mapping (
                    id INTEGER PRIMARY KEY,
                    connection_id INTEGER NOT NULL,
                    linked_calendar_id INTEGER NOT NULL,
                    source_key TEXT NOT NULL,
                    source_label TEXT,
                    target_key TEXT,
                    target_label TEXT,
                    target_color TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    UNIQUE(connection_id, linked_calendar_id, source_key)
                )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS ix_category_import_mapping_connection_id ON category_import_mapping(connection_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS ix_category_import_mapping_linked_calendar_id ON category_import_mapping(linked_calendar_id)")
                now = datetime.utcnow().isoformat(sep=' ')
                cur.execute("SELECT firebase_uid FROM calendar_connection WHERE firebase_uid IS NOT NULL AND TRIM(firebase_uid) != ''")
                for (owner_uid,) in cur.fetchall():
                    cur.execute(
                        "SELECT id FROM personal_calendar WHERE owner_uid=? AND visibility='private' AND archived=0 ORDER BY id ASC LIMIT 1",
                        (owner_uid,),
                    )
                    row = cur.fetchone()
                    if not row:
                        cur.execute(
                            "INSERT INTO personal_calendar(owner_uid, name, color, visibility, archived, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                            (owner_uid, 'My Calendar', '#2563eb', 'private', 0, now, now),
                        )
                # Backfill unit from legacy frequency when null
                try:
                    cur.execute("UPDATE recurring_reminder SET unit='day' WHERE (unit IS NULL OR unit='') AND frequency='daily'")
                    cur.execute("UPDATE recurring_reminder SET unit='week' WHERE (unit IS NULL OR unit='') AND frequency='weekly'")
                    cur.execute("UPDATE recurring_reminder SET unit='month' WHERE (unit IS NULL OR unit='') AND frequency='monthly'")
                except Exception:
                    pass
                conn.commit()
                conn.close()
            except Exception:
                # Best-effort; ignore if anything goes wrong
                pass

    if not app.config.get('TESTING'):
        auth_cfg = (app.config.get('HOMEHUB_CONFIG') or {}).get('auth') or {}
        if auth_cfg.get('mode') == 'firebase':
            cred_path = os.environ.get('FIREBASE_SERVICE_ACCOUNT_FILE', '').strip()
            if cred_path and os.path.isdir(cred_path):
                app.logger.error(
                    'Firebase service account mount is a directory at %s — '
                    'the JSON file was likely missing on first docker compose up. '
                    'Recreate secrets/firebase-service-account.json on the host (see deploy/check-firebase-secret.sh), then '
                    'docker compose -f compose.prod.yml up -d --build --force-recreate',
                    cred_path,
                )
            elif cred_path and not os.path.isfile(cred_path):
                app.logger.error(
                    'Firebase service account not found at %s (check volume mount)',
                    cred_path,
                )

    from .blueprints import main_bp
    # Register modular route modules to attach endpoints to main_bp
    from .blueprints import auth  # noqa: F401
    from .blueprints import dashboard  # noqa: F401
    from .blueprints import notes  # noqa: F401
    from .blueprints import uploads  # noqa: F401
    from .blueprints import shortener  # noqa: F401
    from .blueprints import shopping  # noqa: F401
    from .blueprints import recipes  # noqa: F401
    from .blueprints import expiry  # noqa: F401
    from .blueprints import media_pdfs  # noqa: F401
    from .blueprints import expenses  # noqa: F401
    from .blueprints import chores  # noqa: F401
    from .blueprints import qr  # noqa: F401
    from .blueprints import weather  # noqa: F401
    from .blueprints import calendar_sync  # noqa: F401
    from .blueprints import calendar_page  # noqa: F401
    from .blueprints import school  # noqa: F401
    app.register_blueprint(main_bp)

    if _should_run_background_jobs(app):
        _start_calendar_sync_scheduler(app)

    @app.context_processor
    def inject_auth_state():
        from .user_context import current_display_name, is_logged_in, is_admin, uses_firebase

        return {
            'is_authed': is_logged_in(),
            'auth_mode': (app.config.get('HOMEHUB_CONFIG', {}).get('auth') or {}).get('mode', 'legacy'),
            'uses_firebase': uses_firebase(),
            'current_user_name': current_display_name(),
            'current_user_is_admin': is_admin(),
            'asset_version': resolve_asset_version(app),
        }
    
    # Add Jinja2 filter for JSON parsing
    @app.template_filter('from_json')
    def from_json_filter(s):
        import json
        try:
            return json.loads(s) if s else []
        except (ValueError, TypeError):
            return []

    return app
