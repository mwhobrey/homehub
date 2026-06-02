# Rules & Standards

## Coding conventions

### Python

- **Style:** No formal linter config in repo (no `ruff.toml`, `flake8`, `pyproject.toml`). Match existing files: 4-space indent, double quotes common in newer modules (`user_context.py`, `auth.py`).
- **Imports:** Blueprints use relative imports (`from ..models import …`, `from ..blueprints import main_bp`).
- **Routes:** Decorate `main_bp` in feature files; keep endpoint names as `main.<function_name>` for `url_for` compatibility.
- **Models:** Single `models.py`; new tables need both SQLAlchemy model **and** often a block in `create_app()` SQLite auto-migration section.
- **Identity on writes:** Always use `resolve_actor()` / `resolve_user()` — never read `creator` from the client in Firebase mode.
- **Permissions:** Use `can_modify_record(creator)` and `is_admin()` / `is_admin_for()` before update/delete.
- **User input:** `sanitize_text()` for plain fields; `sanitize_html()` where limited HTML is allowed (notes).
- **URLs for server fetch:** `is_url_safe_for_fetch()` (SSRF guard) in addition to domain allowlists for media.

### Templates & JS

- **Feature visibility:** Guard nav and pages with `config.feature_toggles.get('feature_key')` in `base.html`.
- **Theme:** CSS variables from `config.theme` in `base.html`; respect `data-theme` dark mode.
- **JSON in HTML:** Prefer `|tojson` filter for embedding data (see reminders bootstrap); avoid raw concatenation.
- **CDN assets:** Font Awesome + Google Fonts loaded from CDN in `base.html` (offline/PWA limited without network).

### CSS

- Build before release: `npm run build:css` (Dockerfile and `compose.prod.yml` build run this automatically).
- `static/output.css` is **gitignored** — do not rely on committing it; production CSS comes from the image build.
- Dev watch: `npm run watch:css`.
- Calendar import wizard layout is also inlined in `templates/calendar.html` for dev without a CSS rebuild.
- Config: `tailwind.config.js` content paths include `templates/**/*.html` and `static/js/**/*.js`.

## Error handling

| Situation | Pattern |
|-----------|---------|
| Form validation failure | `flash('message', 'error')` + `redirect` back |
| API unauthorized | `jsonify({'ok': False, 'error': 'unauthorized'}), 401` (`auth.py`) |
| API business logic | `{'ok': False, 'error': '<code>'}` with 4xx |
| Firebase token failure | Log warning, return `invalid_token` 401 |
| SQLite migration block | Broad `try/except: pass` in `__init__.py` — failures are silent (gotcha) |
| Media download failure | Update `Media.status='error'`, store progress text |
| Missing `config.yml` | `FileNotFoundError` at startup from `load_config()` |

**Fail closed** for Firebase allowlist and media URL policy. **Fail open** for legacy LAN when no password and empty creator on edits (`can_modify_record`).

## State management rules

1. **Server session** is the only auth state — do not duplicate auth in localStorage except Firebase client SDK tokens before `POST /auth/session`.
2. **Do not trust client `creator`** when `auth.mode == 'firebase'`.
3. **Config reload** every request reloads `config.yml` — tests set `TESTING=True` to skip this.
4. **Tags** are JSON strings in DB; validate/normalize in route handlers before save.
5. **Recurring engines** (expenses, reminders, chores) use `last_generated_date` / `effective_from` — follow existing generators when adding recurrence fields.

## Testing

### Run locally

```bash
pip install -r requirements.txt
pytest tests/ -q
```

### Conventions

- `make_app()` fixtures override `HOMEHUB_CONFIG` and use in-memory SQLite (`sqlite://`).
- Set `TESTING: True` to skip filesystem DB migrations and config hot-reload side effects.
- Tests assume open auth unless they set `password_hash` or Firebase session manually.

### Gaps

- **CI does not run pytest** — only Docker build on tag push.
- No coverage threshold or lint gate in GitHub Actions.

## Deployment pipelines

| Artifact | Trigger | Output |
|----------|---------|--------|
| Docker image | Tag `v*` or manual workflow | `ghcr.io/<owner>/homehub:latest` + version tags |
| CSS | Inside Docker build + local npm | `static/output.css` |

Operator flows:

- **Quick:** `compose.yml` + volume mounts
- **Prod:** `compose.prod.yml` + external Caddy (`docs/DEPLOY.md`)
- **Prod + Caddy:** `compose.prod.with-caddy.yml`

## Gotchas & technical debt

1. **SQLite ad-hoc migrations** in `app/__init__.py` (~100 lines of `ALTER TABLE` / `CREATE TABLE IF NOT EXISTS`) — not Alembic; easy to miss a migration path for new columns.
2. **`app/routes.py` is dead** — historical; all routes in blueprints.
3. **CSRF disabled** — `WTF_CSRF_ENABLED = False`; new state-changing endpoints need auth + SameSite awareness.
4. **Legacy password = SHA-256** without salt — acceptable for shared family password on LAN; not for internet-facing secrets.
5. **Gunicorn single worker** — background media threads share process; no horizontal scale story.
6. **Flask-Limiter `memory://`** — rate limits reset per process/restart; not shared across workers.
7. **Duplicate path entries on Windows** — repo may show both `app\blueprints\foo.py` and `app/blueprints/foo.py` (same file).
8. **`scripts/refactor_auth*.py`** — untracked one-off codemods; do not run blindly in CI.
9. **SQLAlchemy 2.0 warnings** — `Model.query.get()` still used; migrate to `db.session.get()` over time.
10. **`datetime.utcnow()`** deprecated in Python 3.12 — warnings in tests.
11. **Service worker** caches static assets but bypasses `/api/*` — offline mode shows stale UI for dynamic data.
12. **README vs code:** README still describes older auth; `config-example.yml` and `docs/DEPLOY.md` are authoritative for Firebase.
13. **Google Calendar sync** requires `auth.mode: firebase` and `google_calendar.enabled`; refresh tokens encrypted with `SECRET_KEY` — rotating `SECRET_KEY` invalidates stored tokens (re-connect OAuth). Local dev without `SECRET_KEY` uses stable `data/.secret_key` (gitignored).
14. **HomeHub `RecurringReminder` rules** are not exported to Google in v1; Google recurring events import as expanded instances only.
15. **Windows dev:** `run.py` disables Werkzeug reloader by default; calendar sync timers are daemon threads so Ctrl+C exits cleanly.
16. **Fork deploy:** use `compose.prod.yml` + `docker compose build` — do not pull `ghcr.io/surajverma/homehub:latest` for fork-specific changes.
17. **Config reload on every request** — can hide bugs in tests if `TESTING` not set; small I/O cost in prod.

## Adding a new feature (checklist)

1. Add `feature_toggles.<name>` to `config-example.yml` + `apply_config_defaults` if needed.
2. Create `app/blueprints/<feature>.py` with `@main_bp.route`.
3. Import blueprint in `app/__init__.py`.
4. Add template + sidebar link in `templates/base.html`.
5. Add model(s) in `models.py` + migration block in `__init__.py` if schema changes.
6. Use `resolve_actor` / `can_modify_record` on mutating routes.
7. Add pytest under `tests/` for happy path + auth/sanitize edge case.
