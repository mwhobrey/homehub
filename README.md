# HomeHub (Whobrey fork)

[![CI/CD](https://github.com/mwhobrey/homehub/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/mwhobrey/homehub/actions/workflows/docker-publish.yml)
[![GitHub last commit](https://img.shields.io/github/last-commit/mwhobrey/homehub)](https://github.com/mwhobrey/homehub/commits/main)

> **Fork of [surajverma/homehub](https://github.com/surajverma/homehub)** — extended for a production household deployment (Firebase auth, full calendar, school, to-do lists, in-app settings).  
> **Do not expect `ghcr.io/surajverma/homehub:latest` to include these changes** — build this repo’s image locally or from your own registry.  
> See **[CHANGELOG.md](CHANGELOG.md)** for fork release notes and **[CONTRIBUTING.md](CONTRIBUTING.md)** for development guidelines.

---

# HomeHub: Your All-In-One Family Dashboard

A lightweight, self-hosted web app that turns any computer (even a Raspberry Pi) into a private hub for shared notes, lists, chores, calendar, school, expenses, and more. Designed for families on a **trusted home network**, with an optional **internet-facing** path (Firebase + reverse proxy + hardening).

## Fork upgrades (vs upstream)

| Area | What you get in this fork |
|------|---------------------------|
| **Settings** | **Preferences** (`/settings`) — per-user light/dark/system mode and personal theme colors. **System** (`/settings/system`, admin) — hub name, feature toggles, weather, reminder defaults, **custom sidebar menu labels** (no more editing YAML for routine tweaks). |
| **To-do lists** | Multi-list tasks with sharing, due dates, recurrence, tags, assignees; optional calendar sync (`/todo-lists`). |
| **Calendar** | Full UI at `/calendar` (week grid, drag-reschedule, recurrence, categories). |
| **Google Calendar** | OAuth sync, import wizard, mapping, bidirectional/manual modes (Firebase + `google_calendar` in config). |
| **Personal calendars** | Household + private calendars, sharing, filtered home reminders. |
| **School** | Homeschool module: classes, assignments, submissions, gradebook, attendance (`/school`). |
| **Auth & deploy** | Firebase Google sign-in, allowlists, [`docs/DEPLOY.md`](docs/DEPLOY.md), `compose.prod.yml`, Caddy-oriented production layout. |
| **Security** | Media allowlists, QR encryption, SSRF checks, optional hardening block in config. |

**Chores** remain a simpler household chore list; use **To-do lists** for richer task management.

## What can it do?

Core tools from upstream, plus fork modules above:

- **Shared notes**, **shared cloud**, **shopping list** (with history suggestions)
- **Chores** and **to-do lists**
- **Calendar & reminders** (dashboard widget + full calendar page)
- **Who's home** and **personal status** (dashboard widgets)
- **Expense tracker** (recurring bills, categories)
- **School** (assignments, grading, gradebook)
- **Recipe book**, **expiry tracker**, **URL shortener**, **PDF compressor**, **media downloader**, **QR generator**
- **Weather widget** (Open-Meteo, optional)

## Salient features

- **Private & self-hosted** — data stays on your hardware (SQLite + mounted volumes).
- **Configurable** — `config.yml` for operators; **in-app system settings** for admins; **per-user preferences** for appearance.
- **Feature toggles** — hide sidebar modules without removing routes entirely.
- **PWA** — manifest + service worker for installable / offline-static behavior.

![homehub](https://github.com/user-attachments/assets/55b1c580-8897-4073-9e51-2a892a2bdcd4)

## Quick start (Docker)

1. Copy **`config-example.yml`** → **`config.yml`** and edit (family members, toggles, auth).
2. Use **`compose.yml`** for a simple LAN trial, or **`compose.prod.yml`** + [`docs/DEPLOY.md`](docs/DEPLOY.md) for Firebase + HTTPS.

```yaml
# compose.yml (excerpt)
services:
  homehub:
    image: ghcr.io/surajverma/homehub:latest   # upstream image — fork users should build:
    # build: .                                 # docker compose build
    ports:
      - "5000:5000"
    volumes:
      - ./uploads:/app/uploads
      - ./media:/app/media
      - ./pdfs:/app/pdfs
      - ./data:/app/data
      - ./config.yml:/app/config.yml:ro
```

**This fork:** build from source so you get calendar, school, settings, and related fixes:

```bash
docker compose -f compose.prod.yml up -d --build
```

Open [http://localhost:5000](http://localhost:5000).

<details>
<summary>Example config.yml (abbreviated)</summary>

See **`config-example.yml`** for the full template (Firebase, Google Calendar, school roles, hardening, `nav_labels`, etc.).

```yaml
instance_name: "My Home Hub"

auth:
  mode: legacy   # or firebase for public internet
  allowed_emails: []
  admin_emails: []

feature_toggles:
  calendar: true
  school: true
  todo_list: true
  chores: true
  # ... see config-example.yml

# Optional custom sidebar names (or set in System → Menu labels)
# nav_labels:
#   chores: "Honey-Do"
#   school: "Homeschool"

reminders:
  time_format: 12h
  calendar_start_day: monday

theme:
  primary_color: "#1d4ed8"
  # ... household defaults; users can override in Preferences
```

</details>

## Settings (in-app)

| Page | Path | Who |
|------|------|-----|
| **Preferences** | `/settings` | Each signed-in user — color mode (light / dark / match device), personal theme colors |
| **System** | `/settings/system` | Admins — hub name, feature toggles, weather, reminder display defaults, **menu label renames** |

System changes are stored in SQLite (`app_setting`) and merged over `config.yml` at runtime. **Reset** on the system page clears DB overrides only (does not edit `config.yml` on disk). Auth secrets, hardening, and Google OAuth client IDs remain file/env based.

## Theming

- **Household defaults:** `config.yml` → `theme`
- **Per user:** **Preferences** → appearance + colors (does not change other users’ screens)
- **Dark mode:** user choice or OS (`system`); dark palette still applies tuned surface colors in CSS

Configurable keys are listed in `config-example.yml` under `theme:`.

## Weather widget

Optional dashboard widget via Open-Meteo. Enable in **System settings** or `config.yml` → `weather` (`enabled`, coordinates, `units`, `compact` / `detailed`). See upstream privacy note: requests go to Open-Meteo when enabled.

## Development

Full setup, testing, commit style, and PR checklist: **[CONTRIBUTING.md](CONTRIBUTING.md)**.

```bash
pip install -r requirements.txt
npm install && npm run build:css
cp config-example.yml config.yml
python run.py
```

```bash
pytest tests/ -q    # PYTHONPATH=. on Windows if needed
```

Maintainer/agent docs: [`.cursor/runbook/`](.cursor/runbook/).

## Documentation map

| Document | Purpose |
|----------|---------|
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to develop and open PRs in this fork |
| [CHANGELOG.md](CHANGELOG.md) | Fork feature history and unreleased notes |
| [config-example.yml](config-example.yml) | Authoritative config template |
| [docs/DEPLOY.md](docs/DEPLOY.md) | Firebase, Caddy, production compose |
| [.cursor/runbook/](.cursor/runbook/) | Architecture and file map for maintainers |

## Upstream & attribution

HomeHub was created by [Suraj Verma](https://github.com/surajverma/homehub). This fork retains the MIT license and adds household-specific features listed in [CHANGELOG.md](CHANGELOG.md).

If you find the original project useful, you can [buy the upstream maintainer a coffee ☕](https://ko-fi.com/skv).

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer & security

Software is provided **as is**, without warranty. Intended for **trusted networks** by default.

**Public internet:** use Firebase allowlists, TLS (e.g. Caddy), strong `SECRET_KEY`, and `hardening` options — follow [`docs/DEPLOY.md`](docs/DEPLOY.md). You are responsible for reviewing exposure before going live.

**Weather:** optional third-party API ([Open-Meteo terms](https://open-meteo.com/en/terms)).
