# Contributing to HomeHub (Whobrey fork)

Thank you for helping improve this fork. This document is the source of truth for **how we work in this repository**. The upstream [surajverma/homehub](https://github.com/surajverma/homehub) README is a useful product overview; **fork-specific behavior** is described here, in [`CHANGELOG.md`](CHANGELOG.md), and in [`.cursor/runbook/`](.cursor/runbook/).

## Fork vs upstream

| Topic | This fork (`mwhobrey/homehub`) | Upstream |
|--------|--------------------------------|----------|
| Docker image | **Build locally** — `docker compose -f compose.prod.yml build` | `ghcr.io/surajverma/homehub:latest` |
| Calendar, school, todos, settings UI | Yes | No (as of fork baseline) |
| Production auth | Firebase + optional legacy LAN password | Primarily legacy |
| Operator docs | [`docs/DEPLOY.md`](docs/DEPLOY.md) | README-focused |

Bug fixes that apply upstream should ideally be contributed there first when possible; fork-only features belong in this repo.

## Before you start

1. Read [`config-example.yml`](config-example.yml) and create a local `config.yml` (never commit secrets or real `config.yml`).
2. Skim [`.cursor/runbook/00_INDEX.md`](.cursor/runbook/00_INDEX.md) — table of contents for architecture, file map, conventions, and current state.
3. For deploy or Firebase work, read [`docs/DEPLOY.md`](docs/DEPLOY.md).

## Development setup

```bash
git clone https://github.com/mwhobrey/homehub.git
cd homehub

python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt

cp config-example.yml config.yml   # edit for your household

npm install
npm run build:css                  # required; output.css is gitignored

# Optional: stable local SECRET_KEY + disable background sync jobs
# set HOMEHUB_DISABLE_BACKGROUND_JOBS=1 on Windows/macOS/Linux as needed

python run.py
# → http://localhost:5000
```

Watch CSS during UI work:

```bash
npm run watch:css
```

## Project conventions

### Python / Flask

- **New routes** go in `app/blueprints/<feature>.py` on `main_bp` — not `app/routes.py` (legacy stub).
- **App factory:** `app.create_app()` in `app/__init__.py`.
- **Writes:** use `resolve_actor()` / `resolve_user()`; never trust client `creator` in Firebase mode.
- **Permissions:** `can_modify_record()`, `is_admin()` before mutations.
- **Input:** `sanitize_text()` / `sanitize_html()` from `app/security.py`.
- **Models:** add to `app/models.py` and, if needed, an idempotent SQLite patch block in `app/__init__.py` (no Alembic yet).

### Templates & UI

- Gate sidebar entries with `config.feature_toggles` in `templates/base.html`.
- Sidebar labels: `{{ nav_label('chores') }}` (system overrides + `config.yml` `nav_labels`).
- Theme: `effective_theme` and `user_color_mode` in `base.html`.
- After editing `static/input.css`, run `npm run build:css`.

### Configuration layers

| Layer | What | Who changes it |
|--------|------|----------------|
| `config.yml` | Deploy, auth, secrets, defaults | Operator / file edit |
| System settings UI | Feature toggles, weather, reminders, menu labels | Admin → `/settings/system` |
| User preferences | Light/dark mode, personal colors | Each user → `/settings` |
| `app_setting` table | Persisted UI overrides | Written by settings routes |

Do **not** rewrite `config.yml` from the settings UI.

### New feature checklist

1. `feature_toggles.<name>` in `config-example.yml` and `apply_config_defaults()` if needed.
2. Blueprint + import in `app/__init__.py`.
3. Template + conditional sidebar link in `base.html`.
4. Optional nav label key in `settings_service.NAV_LABEL_DEFAULTS` + `NAV_LABEL_GROUPS`.
5. Tests under `tests/` (happy path + auth/sanitize where relevant).
6. Update [`CHANGELOG.md`](CHANGELOG.md) under `[Unreleased]`.
7. Update runbook (`.cursor/runbook/`) if routes, auth, deploy, or layout change — see [Runbook maintenance](#runbook-maintenance).

## Testing

```bash
# From repo root (Windows PowerShell example)
$env:PYTHONPATH="."
pytest tests/ -q

# Focused
pytest tests/test_settings.py -q
```

- Fixtures use in-memory SQLite and `TESTING: True`.
- **CI does not run pytest today** — run tests locally before opening a PR.

## Commit messages

Use [gitmoji](https://gitmoji.dev) with a conventional prefix:

```text
[JIRA-123] :sparkles: feat(scope): short summary
```

- Omit the `[JIRA-123]` prefix when there is no ticket.
- Use a scope when helpful: `calendar`, `settings`, `school`, `deploy`, `todos`.
- Optional body bullets: `* :bug: detail` (no `Co-authored-by` or other trailers).

Examples:

```text
:sparkles: feat(settings): add sidebar menu label overrides
:bug: fix(calendar): persist PKCE verifier across OAuth redirect
```

## Pull request checklist

- [ ] Focused diff; no unrelated refactors
- [ ] `pytest` passes for affected areas
- [ ] `npm run build:css` if `static/input.css` or Tailwind classes in templates/JS changed
- [ ] `config-example.yml` updated if new config keys are required
- [ ] [`CHANGELOG.md`](CHANGELOG.md) updated under `[Unreleased]`
- [ ] Runbook updated if behavior, routes, or deploy topology changed
- [ ] No secrets, `config.yml`, `data/app.db`, `secrets/`, or `__pycache__` committed
- [ ] No one-off `scripts/refactor_auth*.py` unless explicitly agreed

## Runbook maintenance

When a change affects architecture, routes, config keys, conventions, or feature completeness, add a **minimal factual bullet** to the relevant file under `.cursor/runbook/`:

| Change type | File |
|-------------|------|
| Architecture, auth, deploy, integrations | `01_ARCHITECTURE.md` |
| New/moved modules or routes | `02_COMPONENTS_AND_FILES.md` |
| Conventions, testing, gotchas | `03_RULES_AND_STANDARDS.md` |
| What works / roadmap | `04_CURRENT_STATE.md` |

Agents and maintainers use `.cursorrules` to load these selectively.

## What not to commit

- `config.yml`, `.env`, Firebase service account JSON, OAuth client secrets
- `data/`, `uploads/`, `media/`, `pdfs/` (runtime data)
- `static/output.css` (built in Docker / locally)
- Local codemods in `scripts/refactor_auth*.py` unless promoted to maintained tooling

## Reporting issues

Include:

- Fork commit or approximate date
- `auth.mode` (legacy vs firebase)
- Steps to reproduce
- Expected vs actual behavior
- Relevant `config.yml` fragments (**redact secrets**)

## License

By contributing, you agree that your contributions are licensed under the same [MIT License](LICENSE) as the project.
