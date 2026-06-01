# Deploying HomeHub on a public server (DigitalOcean)

This guide covers the **production stack** added in this repo: **Caddy** (automatic HTTPS) + **HomeHub** + **Firebase Google sign-in** with an email allow list.

## Architecture

```
Internet → :443 Caddy (TLS) → homehub:5000 (Docker internal network)
                ↓
         Firebase verifies Google identity
                ↓
         Flask session (signed cookie) + server-side display name
```

HomeHub is **not** published on host port 5000 in production. Only Caddy exposes 80/443.

## 1. Firebase project

1. Open [Firebase Console](https://console.firebase.google.com/) → **Add project** (or use an existing one).
2. **Authentication** → **Sign-in method** → enable **Google**.
3. **Project settings** → **General** → **Your apps** → add a **Web** app. Copy:
   - API Key  
   - Auth domain  
   - Project ID  
   - App ID  
4. **Project settings** → **Service accounts** → **Generate new private key**. Save the JSON as  
   `secrets/firebase-service-account.json` on the server (never commit this file).

### Authorized domains

In Firebase → **Authentication** → **Settings** → **Authorized domains**, add your public hostname (e.g. `home.yourdomain.com`).

## 2. DNS and droplet

1. Point an **A record** at your droplet IP (`home.yourdomain.com` → droplet).
2. Install Docker and Docker Compose on the droplet.
3. Clone this repo and create data dirs:

```bash
git clone https://github.com/surajverma/homehub.git
cd homehub
mkdir -p uploads media pdfs data secrets
```

## 3. Configuration

```bash
cp .env.example .env
cp config-example.yml config.yml
```

Edit **`.env`**:

| Variable | Example |
|----------|---------|
| `DOMAIN` | `home.yourdomain.com` |
| `ACME_EMAIL` | `you@gmail.com` |
| `SECRET_KEY` | 64-char hex from `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FIREBASE_SERVICE_ACCOUNT_FILE` | `./secrets/firebase-service-account.json` |

Edit **`config.yml`** — set `auth.mode: firebase` and your family:

```yaml
instance_name: "Whobs Family Hub"

auth:
  mode: firebase
  firebase:
    api_key: "AIza..."
    auth_domain: "your-project.firebaseapp.com"
    project_id: "your-project-id"
    app_id: "1:123:web:abc"
  allowed_emails:
    - you@gmail.com
    - spouse@gmail.com
    - kid@gmail.com
  admin_emails:
    - you@gmail.com
  display_names:
    you@gmail.com: "Mike"
    spouse@gmail.com: "Partner"
    kid@gmail.com: "Kid"

# Leave password empty when using Firebase
password: ""

family_members:
  - Mike
  - Partner
  - Kid
```

Only emails in `allowed_emails` can sign in. `admin_emails` can edit expenses settings, site notice, etc.

## 4. Start production stack

```bash
docker compose -f compose.prod.yml up -d --build
```

Check logs:

```bash
docker compose -f compose.prod.yml logs -f caddy
docker compose -f compose.prod.yml logs -f homehub
```

Visit `https://your-domain` → **Continue with Google**.

## 5. Media downloader & QR / WiFi hardening

These features stay enabled but are locked down via `config.yml` → `hardening`:

| Feature | Default behavior |
|---------|------------------|
| **Media downloader** | Only URLs from `allowed_domains` (YouTube/Vimeo by default); SSRF blocked; max file size; 2 concurrent jobs per user; download timeout; rate limit |
| **WiFi QR** | **Not** saved to history (`store_wifi_history: false`) — generate, screenshot/download, done |
| **QR history** | Payloads encrypted at rest; UI shows `WiFi: YourSSID` only; images served at `/qr/image/<id>` (auth required), not public `/static/` |
| **Retention** | History auto-deleted after `history_retention_days` (default 7) |

To let family re-download WiFi QRs from history (less secure), set `hardening.qr_generator.store_wifi_history: true`. Passwords remain encrypted and masked in the UI.

To restrict WiFi QR creation to admins: `admin_only_wifi: true`.

## 6. Security checklist

- [ ] DNS points to droplet before first `up` (Let's Encrypt needs valid DNS).
- [ ] `SECRET_KEY` is long, random, and stable across restarts.
- [ ] `secrets/` is **not** in git; file mode `chmod 600` on service account JSON.
- [ ] UFW: allow `22`, `80`, `443` only.
- [ ] `allowed_emails` lists only real family accounts.
- [ ] Review `hardening.media_downloader.allowed_domains` for sites you actually need.
- [ ] Keep `hardening.qr_generator.store_wifi_history: false` unless you accept stored WiFi credentials (encrypted).
- [ ] Back up `./data`, `./uploads`, `./media`, `./pdfs` regularly.

## Local / LAN (legacy)

`compose.yml` still runs plain HTTP on port 5000. Use `auth.mode: legacy` and optional `password:` for the old shared-password flow.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Certificate errors | Confirm `DOMAIN` matches DNS; ports 80/443 open. |
| `not_allowed` after Google | Add that Gmail address to `allowed_emails`. |
| `invalid_token` | Check service account JSON path and clock sync on server. |
| Redirect loop | Ensure `TRUST_PROXY=1` and Caddy forwards `X-Forwarded-Proto`. |
