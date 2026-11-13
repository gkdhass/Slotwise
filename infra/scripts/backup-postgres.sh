#!/usr/bin/env bash
# Compressed logical backup with a SHA-256 sidecar for restore verification.
#
# Usage:
#   DATABASE_URL=postgresql://user:pass@host:5432/slotwise ./backup-postgres.sh
#   docker compose exec -T postgres ...   (used automatically when no URL is set)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
mkdir -p "$OUT_DIR"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$OUT_DIR/slotwise-${timestamp}.dump"

dump_url="${PG_DUMP_URL:-${DATABASE_URL:-}}"
if [[ -n "$dump_url" ]]; then
  dump_url="${dump_url/postgresql+asyncpg/postgresql}"
  dump_url="${dump_url/postgresql+psycopg/postgresql}"
  pg_dump --format=custom --compress=9 --no-owner --no-privileges \
    --file "$target" "$dump_url"
else
  # Fallback for the private Compose network where PostgreSQL is not published.
  (
    cd "$ROOT_DIR"
    docker compose exec -T postgres pg_dump \
      --format=custom --compress=9 --no-owner --no-privileges \
      --username "${POSTGRES_USER:-slotwise}" \
      --dbname "${POSTGRES_DB:-slotwise}" > "$target"
  )
fi

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$target" > "$target.sha256"
elif command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "$target" > "$target.sha256"
else
  echo "No SHA-256 utility found; refusing to claim an unverified backup" >&2
  rm -f "$target"
  exit 1
fi

# Archive-level integrity check: pg_restore --list parses the TOC without
# touching a database.
pg_restore --list "$target" >/dev/null

echo "backup written: $target"
echo "checksum written: $target.sha256"
