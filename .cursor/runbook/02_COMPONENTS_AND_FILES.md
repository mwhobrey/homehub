# Components & Files

## Top-level directory map

```
homehub/
├── app/                    # Application package
├── templates/              # Jinja2 HTML
├── static/                 # CSS, JS, icons (output.css built)
├── tests/                  # pytest
├── docs/                   # DEPLOY.md (production)
├── deploy/                 # Caddy snippets, Firebase secret check script
├── scripts/                # One-off maintenance (refactor_auth*.py) — not runtime
├── data/                   # SQLite + optional Firebase JSON (gitignored in use)
├── uploads/ media/ pdfs/ # User content volumes
├── config.yml              # Operator config (not in git; from config-example.yml)
├── compose*.yml            # Docker Compose variants
├── Dockerfile              # Production image
├── docker-entrypoint.sh    # Firebase cred copy to /tmp
├── requirements.txt
├── package.json            # Tailwind only
├── wsgi.py                 # Gunicorn entry
└── run.py                  # Dev entry
```

## Application package (`app/`)

| Module | Responsibility |
|--------|----------------|
| `__init__.py` | App factory, DB init, SQLite auto-migrations, blueprint registration, Jinja `from_json` filter, security headers |
| `config.py` | Load/normalize `config.yml` |
| `settings_service.py` | Merge system `app_setting` UI overrides into runtime config |
| `user_preferences_service.py` | Per-user theme + color mode in `app_setting` (`user_prefs:*`) |
| `models.py` | All SQLAlchemy models (single file) |
| `extensions.py` | Flask-Limiter instance |
| `security.py` | bleach sanitization, SSRF URL checks, safe redirect/filename helpers |
| `user_context.py` | Auth mode, session identity, `resolve_actor`, `can_modify_record`, admin checks |
| `school_permissions.py` | School RBAC: teacher/student/parent_observer, class-scoped access |
| `school_services.py` | Gradebook, analytics, audit log, submission helpers |
| `firebase_auth.py` | Firebase Admin init + `verify_id_token` |
| `google_calendar/` | OAuth, Calendar API client, pull/push sync, ACL helpers, import mapping (`imports.py`) |
| `sensitive_store.py` | Fernet encrypt/decrypt (QR payloads, Google OAuth refresh tokens) |
| `media_guard.py` | yt-dlp allowlist, concurrency, command builder |
| `qr_guard.py` | WiFi QR masking, storage preparation |
| `utils.py` | Short URL code generation |
| `routes.py` | **Legacy stub** — docstring only; routes live in blueprints |

## Blueprint modules (`app/blueprints/`)

All routes attach to **`main_bp`** (`blueprints/__init__.py`) — endpoint names like `main.index`, `main.shopping`.

| File | Routes (prefix) | Domain |
|------|-----------------|--------|
| `__init__.py` | `/manifest.webmanifest`, `/sw.js` | PWA |
| `auth.py` | `/login`, `/auth/*`, global `before_app_request` | Auth gate |
| `dashboard.py` | `/`, `/api/reminders*`, `/notice`, `/whoishome`, `/status/*` | Home, reminders API, presence |
| `calendar_page.py` | `/calendar` | Full calendar UI (month/week/agenda + Google setup) |
| `calendar_sync.py` | `/auth/google/calendar/*`, `/api/calendar/*` | Google OAuth + calendar settings/sync + import wizard endpoints |
| `notes.py` | `/notes` | Shared notes |
| `uploads.py` | `/upload`, `/uploads/*` | Shared cloud |
| `shopping.py` | `/shopping`, `/api/shopping*` | Shopping list + tags API |
| `chores.py` | `/chores`, `/api/chores*` | Chores + recurring |
| `todos.py` | `/todo-lists`, `/api/todo-lists*`, `/api/todo-items*` | Multi-list to-dos (share, schedule, recurrence, calendar sync) |
| `todo_calendar_sync.py` | (imported by `todos.py`) | Due dates → `Reminder` rows on selected `PersonalCalendar` |
| `school.py` | `/school`, `/api/school/*` | Homeschool: classes, assignments, submissions, gradebook, attendance |
| `recipes.py` | `/recipes`, `/api/recipes*` | Recipe book |
| `expiry.py` | `/expiry` | Expiry tracker |
| `expenses.py` | `/expenses`, `/api/expenses/month` | Expense tracker |
| `media_pdfs.py` | `/media`, `/pdfs` | Downloader + PDF compressor |
| `shortener.py` | `/shorten`, `/s/<code>` | URL shortener |
| `qr.py` | `/qr` | QR generator |
| `weather.py` | `/api/weather` | Weather proxy/cache |
| `settings.py` | `/settings`, `/settings/system`, reset routes | User preferences (per-user theme/mode) + admin system settings (DB overrides) |

Side-effect imports: `app/__init__.py` imports each blueprint module so decorators register routes.

## Templates (`templates/`)

| Template | Feature |
|----------|---------|
| `base.html` | Layout, sidebar (`nav_label()` overrides), per-user `effective_theme`, SW registration |
| `settings_user.html`, `settings_system.html` | User preferences; admin system settings |
| `index.html` | Dashboard: notice, compact reminders widget, who's home, weather slot |
| `calendar.html` | Full calendar: views, event editor, Google setup tab |
| `login.html` | Legacy password or Firebase |
| `notes.html`, `shopping.html`, `chores.html`, `todos.html`, … | One per feature area |

Shared partial: `_flash.html`.

## Static assets (`static/`)

| Path | Role |
|------|------|
| `input.css` / `output.css` | Tailwind source / built CSS (`npm run build:css` after CSS edits) |
| `js/settings.js`, `js/settings_user.js` | System settings tabs; user preferences (theme, color mode) |
| `js/reminders_api.js` | Reminders + `/api/calendar/*` fetch helpers |
| `js/color_picker.js` | Native color + hex field (`homehubColorPicker`) |
| `js/calendar_app.js` | `/calendar`: month, week time-grid, agenda, lanes, drag-reschedule, recurring |
| `js/calendar_sync.js` | Google connect UI, per-calendar lane color picker, write target |
| `js/personal_calendars.js` | Personal calendar CRUD, share panel, household roster |
| `js/weather.js` | Open-Meteo client |
| `js/firebase-auth.js` | Google sign-in flow |
| `js/tags.js`, `form_tags.js` | Tag UI for shopping/chores/recipes |
| `js/todos.js` | To-do lists SPA (lists, items, shares) |
| `js/school_api.js`, `school_dashboard.js`, `school_assignment.js` | School API client + page logic |
| `js/school_api.js`, `school_dashboard.js`, `school_assignment.js` | School API client + page logic |
| `icons/` | PWA icons, SVG logo |

## Data models (summary)

See `app/models.py` for full schema. Key entities:

- **Collaboration:** `Note`, `ShoppingItem`, `Chore`, `Recipe`, `ExpiryItem`
- **To-do lists:** `TodoList`, `TodoListShare`, `TodoItem`, `RecurringTodoList`, `RecurringTodoItem` (ACL in `app/todo_acl.py`)
- **Files:** `File`, `Media`, `PDF`
- **Household:** `HomeStatus`, `MemberStatus`, `Notice`
- **Scheduling:** `Reminder`, `RecurringReminder`, `RecurringChore`, `PersonalCalendar`, `PersonalCalendarShare`, `CalendarImportProfile`, `CalendarImportMapping`, `CategoryImportMapping`
- **School:** `SchoolClass`, `Enrollment`, `Assignment`, `AssignmentCategory`, `Submission`, `SubmissionArtifact`, `GradeEntry`, `AttendanceRecord`, `SchoolAuditLog`
- **Money:** `RecurringExpense`, `ExpenseEntry`, `app_setting` (key/value, raw SQL)
- **Utilities:** `ShortURL`, `QRCode`, `GroceryHistory`

Tags on shopping/chores/recipes: JSON string in `tags` column, parsed via Jinja `from_json`.

## Configuration locations

| What | Where |
|------|--------|
| Feature toggles, family, theme, weather | `config.yml` → `HOMEHUB_CONFIG` |
| Auth mode, Firebase web config, allowlists | `config.yml` → `auth` |
| Public-internet hardening | `config.yml` → `hardening` |
| Example / defaults | `config-example.yml`, `apply_config_defaults()` |
| Env vars | `.env.example`: `SECRET_KEY`, `DOMAIN`, `MAX_UPLOAD_MB`, `SESSION_DAYS`, Firebase paths |
| Flask app config | `create_app()` in `__init__.py` |
| Runtime chore homepage toggle | DB `app_setting.show_chores_on_homepage` overrides config default |
| Admin UI settings (features, weather, theme, reminders) | `/settings` → `app_setting` keys `settings:*`; merged on each request in `auth.reload_config` |

## Routing & “state management”

- **No React/Vue store.** Server session (`flask.session`) holds auth state only.
- **Feature state:** SQLite + occasional `app_setting` keys.
- **UI state:** Browser localStorage (sidebar collapse, reminder calendar/category visibility toggles), service worker cache, client-side calendar state synced via `/api/reminders`.
- **Context processor** (`__init__.py`): injects `is_authed`, `auth_mode`, `uses_firebase`, `current_user_name`, `current_user_is_admin` into all templates.

## Key environment variables

| Variable | Effect |
|----------|--------|
| `SECRET_KEY` | Session signing, Fernet key material |
| `TRUST_PROXY` | Enables ProxyFix + default secure cookies |
| `SESSION_COOKIE_SECURE` | Force secure cookie |
| `SESSION_DAYS` | `PERMANENT_SESSION_LIFETIME` |
| `MAX_UPLOAD_MB` | `MAX_CONTENT_LENGTH` |
| `FIREBASE_SERVICE_ACCOUNT_FILE` / `JSON` | Admin SDK credentials |
| `FIREBASE_CREDENTIALS_SRC` | Host path for entrypoint copy |
| `SW_CACHE_VERSION` | Service worker cache bust (else git tag) |
| `HOMEHUB_BIND` | Prod compose port binding |
| `PROXY_NETWORK` | External Docker network for Caddy |
| `HOMEHUB_DISABLE_BACKGROUND_JOBS` | Skip calendar sync scheduler (local dev) |
| `FLASK_USE_RELOADER` | `auto` (off on Windows), `0`/`1` to override |
| `FLASK_DEBUG` | Local dev debugger (`run.py`) |

## Tests map

| File | Covers |
|------|--------|
| `test_security.py` | XSS sanitization, reminder API bootstrap |
| `test_feature_hardening.py` | Media allowlist, QR WiFi masking, encryption |
| `test_expenses.py` | Recurring expense generation |
| `test_recurring_reminders.py` | Reminder recurrence + personal calendar on rules |
| `test_personal_calendar_sharing.py` | Share ACL, visibility filtering |
| `test_personal_calendars_api.py` | Personal calendar CRUD + shares API |
| `test_recurring_chores.py` | Chore recurrence |
| `test_reminder_conversion.py` | Single ↔ recurring conversion |
| `test_shopping_chores_tags.py` | Tags API + filters |
