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

By default, HomeHub binds to **`127.0.0.1:5000`** only. Your **existing** Caddy (or other proxy) terminates TLS on 80/443 and forwards to that address.

If this server has **no** reverse proxy yet, use `compose.prod.with-caddy.yml` (see below).

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
| Firebase service account | `secrets/firebase-service-account.json` on host → `/run/secrets/` in container |

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

## 4. Start HomeHub (existing Caddy on 80/443)

If you already run Caddy (or another proxy), **do not** start a second one — that causes `port is already allocated`.

```bash
# Stop/remove the failed stack if you tried the old all-in-one compose
docker compose -f compose.prod.yml down 2>/dev/null || true
docker rm -f homehub-caddy 2>/dev/null || true

docker compose -f compose.prod.yml up -d --build
docker compose -f compose.prod.yml logs -f homehub
```

HomeHub is on **`127.0.0.1:5000`** (override with `HOMEHUB_BIND` in `.env`).

### Wire your existing Caddy

Copy the site block from `deploy/Caddyfile.snippet` into your Caddy config, then reload Caddy:

```bash
# Examples — use whatever you normally do:
caddy reload --config /path/to/Caddyfile
# or: docker exec <your-caddy-container> caddy reload --config /etc/caddy/Caddyfile
```

| Your Caddy runs… | `reverse_proxy` target |
|------------------|------------------------|
| On the host (systemd) | `127.0.0.1:5000` |
| In Docker | `host.docker.internal:5000` or `172.17.0.1:5000` |
| Headscale / shared proxy network | `homehub:5000` — set `PROXY_NETWORK` in HomeHub `.env` (usually `reverseproxy-nw`; confirm with `docker inspect caddy`) |

Visit `https://your-domain` → **Continue with Google**.

### No existing Caddy?

```bash
docker compose -f compose.prod.with-caddy.yml up -d --build
```

Uses `deploy/Caddyfile` and requires free ports 80/443.

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
| `Firebase credentials missing` on sign-in | See below |

### Firebase sign-in: credentials missing

Inside the container the file must be **`/run/secrets/firebase-service-account.json`** (host: `secrets/firebase-service-account.json`).

```bash
# On the host — must be a real JSON file before compose up
ls -la secrets/firebase-service-account.json
file secrets/firebase-service-account.json

# Inside the container
docker exec homehub ls -la /run/secrets/
docker exec homehub head -1 /run/secrets/firebase-service-account.json   # should show {

docker exec homehub printenv FIREBASE_SERVICE_ACCOUNT_FILE
# /run/secrets/firebase-service-account.json
```

**`head: I/O error`** on the old single-file mount (`firebase-sa.json`) means the bind mount is broken — usually the host file was missing on first `up`, or you replaced the JSON while the container was running. Fix:

```bash
cd ~/homehub
git pull   # compose mounts ./secrets -> /run/secrets (directory mount)
docker compose -f compose.prod.yml down
ls -la secrets/firebase-service-account.json   # must be a file
chmod 600 secrets/firebase-service-account.json
docker compose -f compose.prod.yml up -d --force-recreate
docker exec homehub head -1 /run/secrets/firebase-service-account.json
```

`root:root` with mode `600` is fine — the app runs as root in the image.
