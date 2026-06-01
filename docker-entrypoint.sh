#!/bin/sh
# Copy Firebase credentials into /tmp so reads never hit a stale single-file bind mount.
set -eu

DST="/tmp/firebase-sa.json"

try_load() {
    path="$1"
    if [ ! -f "$path" ]; then
        return 1
    fi
    if ! cat "$path" >/dev/null 2>&1; then
        echo "homehub-entrypoint: cannot read $path (I/O error on host mount — recreate the file; see docs/DEPLOY.md)" >&2
        return 1
    fi
    cp "$path" "$DST"
    chmod 600 "$DST"
    export FIREBASE_SERVICE_ACCOUNT_FILE="$DST"
    echo "homehub-entrypoint: Firebase credentials loaded from $path" >&2
    return 0
}

SRC="${FIREBASE_CREDENTIALS_SRC:-/app/credentials/firebase-service-account.json}"

if try_load "$SRC"; then
    :
elif try_load /app/data/firebase-service-account.json; then
  echo "homehub-entrypoint: using /app/data/firebase-service-account.json (consider fixing secrets/ mount)" >&2
else
    echo "homehub-entrypoint: no readable Firebase service account file found" >&2
fi

exec "$@"
