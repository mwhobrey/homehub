# Current State

*Snapshot based on repo at `main` (~bd44ed4 deploy/Firebase fixes). Re-verify before relying on dates.*

## What is working

### Core product

- All feature modules listed in README are implemented as Flask routes + templates (notes, upload, shopping, chores, recipes, expiry, expenses, media, PDFs, shortener, QR, dashboard).
- **School module** (`/school`): classes, enrollments, assignments with deadlines, student submissions (file upload + external links), teacher grading/feedback, weighted gradebook, attendance, analytics; config under `school:` and toggle `feature_toggles.school`.
- **Dedicated calendar** at `/calendar`: week time-grid, drag-reschedule, resize duration, recurring (RRULE export to Google), per-event timezone + attendees, sync conflict resolution UI, calendar lane filters, full color picker.
- **Feature toggles** in `config.yml` hide sidebar entries without removing routes entirely (routes still exist if URL known).
- **SQLite persistence** with automatic table creation and incremental column migrations on startup.
- **Tailwind UI** with config-driven theming and dark/light system preference.
- **PWA:** manifest + service worker with versioned cache.

### Auth & deploy (recent focus)

- **Legacy mode:** optional shared password (SHA-256), session cookie, rate-limited login.
- **Firebase mode:** Google sign-in, email allowlist, admin emails, display name mapping, `/auth/session` token exchange.
- **Google Calendar sync (optional):** Bidirectional sync when `google_calendar.enabled` + Firebase; OAuth at `/auth/google/calendar/start`; per-calendar visibility (private / household / custom shares); aggregate dashboard view with per-user display filters and per-save write calendar selection.
- **Production compose:** `compose.prod.yml` (localhost bind + proxy network), optional Caddy stack, `docker-entrypoint.sh` copies Firebase SA to `/tmp`.
- **Hardening:** media domain allowlist + concurrency limits, QR payload encryption, WiFi masking (`test_feature_hardening.py`).

### Quality

- **`pytest tests/`:** includes `test_school.py` (permissions, submissions, gradebook, attendance).
- **Docker publish workflow** builds CSS and multi-arch images on `v*` tags.

## What is incomplete, weak, or operational-only

| Area | Status |
|------|--------|
| **CI test gate** | No automated pytest in GitHub Actions |
| **Formal migrations** | No Alembic; raw SQLite patches only |
| **Internet-safe by default** | LAN-open without password; public deploy requires Firebase + proxy + hardening config |
| **CSRF** | Disabled project-wide |
| **Rate limiting** | In-memory only; single gunicorn worker |
| **Maintainer bandwidth** | README disclaimer: solo maintainer, slow PR/issue response |
| **Auth refactor scripts** | `scripts/refactor_auth*.py` untracked — local tooling, not product |

Nothing in-tree flags a specific feature as “broken”; gaps are **process and hardening**, not missing route stubs.

## Immediate next steps (suggested)

Ordered by impact for this fork (`whobs/dev/homehub` on `main`):

1. **Operator validation** — If deploying publicly: complete `docs/DEPLOY.md` checklist (Firebase authorized domains, `SECRET_KEY`, Caddy snippet, `secrets/firebase-service-account.json` via `deploy/check-firebase-secret.sh`).
2. **CI hygiene** — Add a `pytest` job to `.github/workflows/docker-publish.yml` (or separate workflow) so releases cannot ship failing tests.
3. **Runbook hygiene** — When landing auth/feature/deploy changes, update the relevant runbook section (see `.cursorrules`).
4. **SQLAlchemy cleanup** — Replace `Model.query.get()` and `utcnow()` to silence 2.0/3.12 warnings before they become errors.
5. **Delete or document `scripts/refactor_auth*.py`** — Either commit with README note or remove from workspace to avoid accidental runs.
6. **Optional:** Alembic or consolidated migration script to replace the growing `__init__.py` SQLite block.

## Verification commands

```bash
# Tests
pytest tests/ -q

# CSS
npm install && npm run build:css

# Local app (requires config.yml)
python run.py

# Docker prod stack
docker compose -f compose.prod.yml up -d --build
```

## Branch / git notes

- Current branch observed: `main`.
- Recent commits center on **deploy + Firebase credential mounting** and **security/hardening** feature set.
- Untracked: `scripts/refactor_auth.py`, `refactor_auth_pass2.py`, `refactor_auth_patterns.py` (not part of published image unless added).
