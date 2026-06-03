# Changelog

All notable changes to **[mwhobrey/homehub](https://github.com/mwhobrey/homehub)** (this fork) are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

This fork extends **[surajverma/homehub](https://github.com/surajverma/homehub)**. Upstream release history is not duplicated here; see the [upstream repository](https://github.com/surajverma/homehub) for earlier versions.

## [Unreleased]

### Added

- (Nothing yet — add entries here before the next tagged release.)

## [2026.06] — Fork feature set (on `main`)

Summary of major capabilities added after the production-auth / hardening baseline (`148ff72`).

### Added

- **In-app settings** — `/settings` (per-user preferences: light/dark/system appearance, personal theme colors) and `/settings/system` (admin: hub name, feature toggles, weather, reminder defaults, **custom sidebar menu labels**). System values persist in SQLite `app_setting` and merge over `config.yml` without rewriting the file.
- **To-do lists** (`/todo-lists`) — Multiple lists, sharing (Firebase ACL), due dates, recurrence, tags, assignees; optional sync of open due dates to personal calendar reminders (`feature_toggles.todo_list`).
- **School / homeschool module** (`/school`) — Classes, enrollments, assignments, submissions, grading, gradebook, attendance, analytics (`feature_toggles.school`).
- **Full calendar UI** (`/calendar`) — Month/week/agenda, drag-reschedule, duration resize, recurring events (RRULE toward Google), time zones, attendees, lane filters, color picker.
- **Google Calendar integration** — OAuth (Firebase required), import-first wizard, per-calendar mapping, category/color import, sync modes (`import_only`, bidirectional, `manual`), disconnect flow.
- **Personal calendars** — Household + private calendars, share ACL, home reminder visibility pills, calendar-scoped reminder filtering.
- **Firebase authentication** — Google sign-in, email allowlist, admin emails, display-name mapping, production deploy path ([`docs/DEPLOY.md`](docs/DEPLOY.md)).
- **Public deployment stack** — `compose.prod.yml`, optional Caddy compose, Firebase service-account entrypoint, media/QR hardening knobs in `config.yml`.

### Changed

- **Chores** remain a separate simple tracker; multi-list task management lives under **To-do lists**.
- **Config reload** merges `app_setting` overrides on every request (including `TESTING` merge path for DB overrides).
- **Theming** — Household defaults from `config.yml`; per-user overrides via Preferences; sidebar labels via `nav_label()` / `nav_labels` / System → Menu labels.

### Fixed

- Google Calendar OAuth (PKCE verifier persistence, scope alignment, incomplete state, disconnect).
- Deploy: Firebase SA mount/copy, Google Calendar OAuth env in container, calendar DOM init order.
- Calendar import wizard UX and local dev ergonomics (`run.py` reloader, background jobs toggle).

### Security

- Optional internet-facing posture: Firebase allowlist, SSRF checks, media domain allowlist, encrypted QR payloads, WiFi QR masking (see `hardening` in `config-example.yml` and `tests/test_feature_hardening.py`).

---

## How to maintain this file

1. Add user-facing changes under **`[Unreleased]`** as you land work.
2. On a tagged release, rename `[Unreleased]` to `[x.y.z] - YYYY-MM-DD` and start a fresh `[Unreleased]` section.
3. Prefer **Added / Changed / Fixed / Security** groupings and write for operators and family admins, not only developers.
