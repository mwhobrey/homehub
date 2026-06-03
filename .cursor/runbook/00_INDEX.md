# HomeHub Master Runbook — Index

## Executive summary

**HomeHub** is a self-hosted, family-oriented web dashboard: one Flask app that bundles shared notes, file uploads, shopping lists, chores, calendar/reminders, recipes, expiry tracking, expenses, media downloads (yt-dlp), PDF compression, URL shortening, QR codes, and an optional weather widget. Data stays on your machine (SQLite + volume-mounted files). It targets **trusted home LANs** by default, with a **production path** (Firebase Google sign-in, Caddy TLS, domain allowlists, SSRF/media/QR hardening) for limited public exposure.

## North Star

> Give every household member a **single, private, low-friction hub** on their own network (or carefully exposed host) to coordinate daily family life—without SaaS lock-in, ads, or shipping personal data to a vendor.

Success means: non-technical family members can use it daily; operators can deploy and harden it with `config.yml` + Docker; contributors can extend one feature without breaking others.

## How to use this runbook

| If you are… | Read first |
|-------------|------------|
| New to the repo | This file → [01_ARCHITECTURE.md](./01_ARCHITECTURE.md) → [02_COMPONENTS_AND_FILES.md](./02_COMPONENTS_AND_FILES.md) |
| Changing auth / deploy / security | [01_ARCHITECTURE.md](./01_ARCHITECTURE.md) → [03_RULES_AND_STANDARDS.md](./03_RULES_AND_STANDARDS.md) → `docs/DEPLOY.md` |
| Adding or fixing a feature | [02_COMPONENTS_AND_FILES.md](./02_COMPONENTS_AND_FILES.md) → relevant blueprint in `app/blueprints/` |
| Planning work / triage | [04_CURRENT_STATE.md](./04_CURRENT_STATE.md) |

Keep context small: **do not load all runbook files** unless the task crosses concerns (e.g. auth + media + deploy).

## Table of contents

| File | Contents |
|------|----------|
| [00_INDEX.md](./00_INDEX.md) | Summary, North Star, this TOC |
| [01_ARCHITECTURE.md](./01_ARCHITECTURE.md) | Stack, patterns, data flow, external APIs |
| [02_COMPONENTS_AND_FILES.md](./02_COMPONENTS_AND_FILES.md) | Directory map, modules, routing, config locations |
| [03_RULES_AND_STANDARDS.md](./03_RULES_AND_STANDARDS.md) | Conventions, errors, state, tests, CI, gotchas |
| [04_CURRENT_STATE.md](./04_CURRENT_STATE.md) | Working vs incomplete, next steps |

## Quick facts

- **Contributor docs:** [`CONTRIBUTING.md`](../CONTRIBUTING.md), [`CHANGELOG.md`](../CHANGELOG.md), [`README.md`](../README.md) (fork overview)
- **Entry:** `wsgi.py` / `run.py` → `app.create_app()`
- **Config:** `config.yml` (from `config-example.yml`); loaded by `app/config.py`
- **DB:** SQLite at `data/app.db` (auto `create_all` + inline SQLite migrations in `app/__init__.py`)
- **UI:** Jinja2 templates + Tailwind-built `static/output.css`
- **Auth:** `legacy` (optional shared password) or `firebase` (Google via Firebase Admin + client SDK)
- **Tests:** `pytest tests/` (31 tests at last runbook write; no pytest in CI workflow)
- **Ship:** Docker → GHCR on version tags (`v*`); gunicorn in container

## Related repo docs

- `README.md` — user-facing features and Docker quick start
- `docs/DEPLOY.md` — Firebase + Caddy + production compose
- `config-example.yml` — all toggles and hardening defaults
