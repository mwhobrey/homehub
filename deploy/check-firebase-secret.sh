#!/usr/bin/env bash
# Run on the HomeHub host (not inside the container).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SECRET_HOST="$ROOT/secrets/firebase-service-account.json"
SECRET_DATA="$ROOT/data/firebase-service-account.json"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

check_file() {
  local path="$1"
  echo "==> $path"
  if [ ! -e "$path" ]; then
    echo "    missing"
    return 1
  fi
  if [ -d "$path" ]; then
    echo "    is a DIRECTORY (Docker artifact) — remove and place a real JSON file"
    return 1
  fi
  if ! file "$path" | grep -q 'JSON\|ASCII\|text'; then
    file "$path"
  fi
  if ! head -1 "$path" | grep -q '{'; then
    echo "    does not look like JSON"
    return 1
  fi
  echo "    OK ($(wc -c <"$path") bytes)"
  return 0
}

echo "HomeHub Firebase credential check"
echo

ok=0
if check_file "$SECRET_HOST"; then
  ok=1
fi
if check_file "$SECRET_DATA"; then
  ok=1
fi

if [ "$ok" -eq 0 ]; then
  echo
  fail "No valid service account JSON. Fix with:

  docker compose -f compose.prod.yml down
  rm -rf secrets/firebase-service-account.json   # only if directory or broken
  mkdir -p secrets data
  # Copy fresh JSON from Firebase Console -> Project settings -> Service accounts
  nano secrets/firebase-service-account.json
  chmod 600 secrets/firebase-service-account.json

  # Or use the data volume (often more reliable):
  cp /path/to/your-firebase-sa.json data/firebase-service-account.json
  chmod 600 data/firebase-service-account.json

  docker compose -f compose.prod.yml up -d --build --force-recreate
"
fi

echo
echo "Recreate container after fixing files:"
echo "  docker compose -f compose.prod.yml up -d --build --force-recreate"
echo "  docker exec homehub head -1 /tmp/firebase-sa.json"
