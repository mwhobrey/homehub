# Google Calendar sync — operator & family setup guide

This guide covers everything you must do **outside the codebase** to turn on bidirectional Google Calendar sync in HomeHub. Use it alongside [DEPLOY.md](./DEPLOY.md) (Firebase + TLS).

**Code reference:** sync is enabled when `auth.mode: firebase` and `google_calendar.enabled: true`. Implementation lives under `app/google_calendar/` and `app/blueprints/calendar_sync.py`.

---

## Table of contents

1. [Prerequisites](#1-prerequisites)
2. [Google Cloud & OAuth consent screen](#2-google-cloud--oauth-consent-screen)
3. [Privacy policy URL (required for OAuth)](#3-privacy-policy-url-required-for-oauth)
4. [HomeHub configuration](#4-homehub-configuration)
5. [Deploy and restart](#5-deploy-and-restart)
6. [Per-family-member onboarding](#6-per-family-member-onboarding)
7. [Privacy: adults vs teen calendars](#7-privacy-adults-vs-teen-calendars)
8. [Smoke-test checklist](#8-smoke-test-checklist)
9. [Ongoing operations](#9-ongoing-operations)
10. [Troubleshooting](#10-troubleshooting)
11. [Known limitations (v1)](#11-known-limitations-v1)

---

## 1. Prerequisites

| Requirement | Why |
|---------------|-----|
| **`auth.mode: firebase`** in `config.yml` | Calendar sync is Firebase-only. Legacy shared-password mode does not show connect UI or store per-user OAuth tokens. |
| **Firebase Google sign-in working** | Same flow as production deploy ([DEPLOY.md](./DEPLOY.md)). |
| **`allowed_emails` configured** | Only listed accounts can log in and connect Google. |
| **Stable `SECRET_KEY`** | Google refresh tokens are encrypted with Fernet derived from `SECRET_KEY`. **Rotating `SECRET_KEY` invalidates stored tokens** — everyone must reconnect Google Calendar. |
| **HTTPS in production** | OAuth redirect URIs must match exactly (scheme + host + path). |

---

## 2. Google Cloud & OAuth consent screen

Use the **same GCP project as Firebase** when possible.

### 2.1 Enable the API

1. Open [Google Cloud Console](https://console.cloud.google.com/) → select your project.
2. **APIs & Services → Library** → search **Google Calendar API** → **Enable**.

### 2.2 OAuth consent screen

**APIs & Services → OAuth consent screen**

| Field | What to enter |
|--------|----------------|
| **User type** | **External** (typical family hub on the public internet). Use **Internal** only if every user is in your Google Workspace org. |
| **App name** | e.g. `Whobs Family Hub` |
| **User support email** | Your email |
| **Developer contact** | Your email |
| **App logo** | Optional |
| **Application home page** | `https://home.yourdomain.com/` (your real HomeHub URL) |
| **Application privacy policy link** | `https://home.yourdomain.com/privacy` (see [§3](#3-privacy-policy-url-required-for-oauth)) |
| **Application terms of service link** | `https://home.yourdomain.com/terms` (recommended; see §3) |
| **Authorized domains** | `yourdomain.com` (domain only, no path) |

**Scopes**

- Add (or verify): `https://www.googleapis.com/auth/calendar`  
  (Full read/write — required for bidirectional sync.)

**Test users (while app status is “Testing”)**

- Add every Gmail address listed in `config.yml` → `auth.allowed_emails`.
- Users not listed as test users will see **access blocked** until you publish the app.

**Publishing**

- For a private family server you can stay in **Testing** with test users only.
- If Google requests verification for sensitive scopes, you may need to submit for review or keep the app in testing with explicit test users.

### 2.3 OAuth client (Web)

**APIs & Services → Credentials → Create credentials → OAuth client ID → Web application**

**Authorized JavaScript origins** (recommended):

- `https://home.yourdomain.com`
- `http://localhost:5000` (local dev only)

**Authorized redirect URIs** (required — character-for-character match):

- `https://home.yourdomain.com/auth/google/calendar/callback`
- `http://localhost:5000/auth/google/calendar/callback` (local dev)

Copy the **Client ID** and **Client secret**.

---

## 3. Privacy policy URL (required for OAuth)

Google’s OAuth consent screen requires a **publicly accessible privacy policy URL**. HomeHub ships static legal pages you can point Google at:

| Page | URL |
|------|-----|
| Privacy policy | `https://home.yourdomain.com/privacy` |
| Terms of use | `https://home.yourdomain.com/terms` |

### 3.1 Before you paste URLs into Google

1. Deploy HomeHub behind HTTPS with your real hostname.
2. Open `https://home.yourdomain.com/privacy` in a browser (no login required).
3. **Edit the templates** so they match your household:
   - [`templates/privacy.html`](../templates/privacy.html) — operator name, contact email, jurisdiction if you care.
   - [`templates/terms.html`](../templates/terms.html) — same.
4. Set contact info in `config.yml` under `legal` (optional but recommended):

   ```yaml
   legal:
     contact_email: "you@gmail.com"
     policy_updated: "2026-06-01"
   ```

6. Re-deploy after edits.

These pages describe a **self-hosted family dashboard**: you (the operator) run the server; data stays on your infrastructure except where third-party services (Google, Firebase) are used by design.

### 3.2 What to put in Google Cloud

| OAuth consent field | Value |
|---------------------|--------|
| Privacy policy | `https://<your-domain>/privacy` |
| Terms of service | `https://<your-domain>/terms` |
| Home page | `https://<your-domain>/` |

### 3.3 If you use a different privacy policy

You may host policy text elsewhere (GitHub Pages, Notion, etc.) as long as the URL is **public HTTPS** and accurately describes your deployment. Update Google Cloud to that URL instead of `/privacy`.

---

## 4. HomeHub configuration

Edit **`config.yml`** at the repo root (from `config-example.yml`):

```yaml
auth:
  mode: firebase
  firebase:
    api_key: "..."
    auth_domain: "..."
    project_id: "..."
    app_id: "..."
  allowed_emails:
    - you@gmail.com
    - spouse@gmail.com
    # ...

google_calendar:
  enabled: true
  client_id: "YOUR_CLIENT_ID.apps.googleusercontent.com"
  client_secret: ""   # prefer environment variable (below)
  sync_interval_minutes: 15
  default_timezone: "America/Chicago"
  onboarding_all_calendars_enabled: true
```

**Secrets (recommended for production)**

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CALENDAR_CLIENT_SECRET` | OAuth client secret (overrides yaml if set) |
| `GOOGLE_CALENDAR_CLIENT_ID` | Optional override for client id |
| `SECRET_KEY` | Session + token encryption (already required for prod) |

Do **not** commit `config.yml` with real secrets to git.

---

## 5. Deploy and restart

### Local development

```powershell
cd path\to\homehub
pip install -r requirements.txt
python run.py
```

Use `http://localhost:5000` and the localhost redirect URI in GCP.

### Docker / production

1. Rebuild the image or reinstall Python deps (new packages: `google-api-python-client`, `google-auth-oauthlib`, `google-auth`).
2. Set `GOOGLE_CALENDAR_CLIENT_ID` and `GOOGLE_CALENDAR_CLIENT_SECRET` in `.env`    (see `.env.example`). Compose passes them into the container — a secret only in host `.env` without that wiring will fail at OAuth callback with `client_secret is missing`.
3. Restart the stack with recreate so env is picked up: `docker compose -f compose.prod.yml up -d --force-recreate`
4. Confirm Firebase **Authorized domains** includes your public hostname.
5. Verify `/privacy` loads over HTTPS before finishing OAuth consent screen setup.

---

## 6. Per-family-member onboarding

Each person on `allowed_emails` should complete these steps **once**, with **their own** Google account:

1. Sign in to HomeHub via Firebase (normal login).
2. On the dashboard **Reminders** card:
   - Click **Connect Google Calendar**, or
   - Visit `/auth/google/calendar/start` while logged in.
3. Approve Google calendar access on the consent screen.
4. After redirect, open **Google Calendars** (collapsible panel):
   - Confirm calendars appear.
   - Set **Default write calendar** (where new events go by default).
   - Toggle **Sync** per calendar.
   - Set **Visibility**: `private`, `household`, or `custom`.
5. Click **Sync now** and confirm events show on the calendar grid.

**Creating/editing reminders**

- **Save to calendar** dropdown defaults to your default calendar; pick another owned calendar per save if needed.
- Events push to Google when you have an active connection.

---

## 7. Privacy: adults vs teen calendars

Two independent controls:

| Layer | Who controls | Effect |
|--------|----------------|--------|
| **Visibility ACL** | Calendar owner | Who is *allowed* to see events (`private` / `household` / `custom` + shares). |
| **Display filter** | Each viewer | Of calendars you *may* see, which appear on *your* dashboard (checkbox). |

### Suggested patterns

| Goal | Setting |
|------|---------|
| Only I see this calendar | Visibility → **private** |
| All logged-in family members see it | Visibility → **household** |
| Only spouse (not teen) | Visibility → **custom** + shares (below) |

### Custom shares (API today)

The manager UI sets visibility to `custom` when you configure shares via API. Example (while logged in as calendar owner):

```http
PUT /api/calendar/calendars/<linked_calendar_id>/shares
Content-Type: application/json

{
  "shares": [
    { "grantee_uid": "SPOUSE_FIREBASE_UID", "can_write": false }
  ]
}
```

**Finding `grantee_uid`:** after each person connects Google Calendar, their UID is stored in SQLite table `calendar_connection` column `firebase_uid`. A future UI may list household members by email; for now use DB or admin tooling.

`can_write: false` prevents HomeHub from pushing that teen’s edits into your Google calendar (v1 default).

---

## 8. Smoke-test checklist

Run as Parent A, Parent B, and Teen (if applicable):

- [ ] Connect → calendars import; primary is default write target.
- [ ] “Adults” calendar **private** → teen does not see events.
- [ ] Parent B hides “Work” via display filter → hidden for B only.
- [ ] Create on default calendar → appears in HomeHub and Google Calendar app.
- [ ] Create on “School” via dropdown → correct Google calendar.
- [ ] Edit → change **Save to calendar** → event moves in Google.
- [ ] Edit in Google → **Sync now** (or wait `sync_interval_minutes`) → HomeHub updates.
- [ ] Edit/delete in HomeHub → Google updates.
- [ ] Disconnect tested only if desired (`POST /api/calendar/disconnect`).

---

## 9. Ongoing operations

| Task | Action |
|------|--------|
| Force sync | Dashboard → **Sync now**, or `POST /api/calendar/sync` |
| New family member | Add to `allowed_emails` + OAuth test users; they log in and connect Google |
| Token invalid after secret rotation | Each user: **Connect Google Calendar** again |
| Backup | Copy `data/app.db` (events + encrypted tokens) with your usual backup |

---

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| `client_secret is missing` on OAuth callback | Secret not in container env or `config.yml` | Set `GOOGLE_CALENDAR_CLIENT_SECRET` in `.env` **and** pass it in `compose.prod.yml` `environment:` (or put `client_secret` in `config.yml`); recreate container |
| `redirect_uri_mismatch` | GCP redirect URI ≠ actual callback URL | Fix URI in Credentials; include exact path `/auth/google/calendar/callback` |
| `access_denied` / app blocked | User not on OAuth **test users** list | Add Gmail in consent screen, or publish app |
| `google_calendar_disabled` API | `enabled: false` or not Firebase mode | Check `config.yml` |
| `invalid_calendar` on save | Wrong `linked_calendar_id` or not your calendar | Use dropdown; only owned calendars |
| No connect banner | `google_calendar.enabled: false` or not Firebase | Config + template flags |
| Privacy policy rejected by Google | URL not public or 404 | Deploy `/privacy`; verify in incognito |
| Events never update | Sync not running | **Sync now**; check `last_sync_at`; logs for `pull_calendar failed` |
| Everyone must re-auth Google | `SECRET_KEY` changed | Re-run Connect Google Calendar |

---

## 11. Known limitations (v1)

- **HomeHub `RecurringReminder` rules** do not export to Google; they stay local. Google recurring events import as expanded instances (±12 month window on first/full sync).
- **Auto-redirect** to connect calendar after Firebase login is not enforced; use the banner or `/auth/google/calendar/start`.
- **Custom share picker UI** is partial; grantee UIDs may require API/DB (see §7).
- **CI** does not run pytest on GitHub Actions by default; locally:  
  `$env:PYTHONPATH='.'; pytest tests/ -q` (PowerShell)

---

## Quick reference — URLs to register in Google Cloud

Replace `home.yourdomain.com` with your hostname:

```
Home page:     https://home.yourdomain.com/
Privacy:       https://home.yourdomain.com/privacy
Terms:         https://home.yourdomain.com/terms
Redirect URI:  https://home.yourdomain.com/auth/google/calendar/callback
```

Local dev redirect:

```
http://localhost:5000/auth/google/calendar/callback
```
