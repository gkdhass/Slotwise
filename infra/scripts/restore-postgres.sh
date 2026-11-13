#!/usr/bin/env bash
# Restore a compressed backup only after checksum + archive TOC verification.
# Refuses to overwrite a non-empty public schema unless --force is supplied.
#
# Usage:
#   DATABASE_URL=postgresql://user:pass@host:5432/slotwise ./restore-postgres.sh FILE
#   ./restore-postgres.sh FILE --force
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: restore-postgres.sh <dump-file> [--force]" >&2
  exit 1
fi

dump_file="$1"
force="${2:-}"
checksum_file="${dump_file}.sha256"

if [[ ! -f "$dump_file" ]]; then
  echo "dump not found: $dump_file" >&2
  exit 1
fi
if [[ ! -f "$checksum_file" ]]; then
  echo "checksum sidecar missing; refusing an unverified restore" >&2
  exit 1
fi

# Verify the sidecar against the actual bytes before parsing the archive.
if command -v sha256sum >/dev/null 2>&1; then
  expected="$(awk '{print $1}' "$checksum_file")"
  actual="$(sha256sum "$dump_file" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  expected="$(awk '{print $1}' "$checksum_file")"
  actual="$(shasum -a 256 "$dump_file" | awk '{print $1}')"
else
  echo "No SHA-256 utility found; refusing an unverified restore" >&2
  exit 1
fi
if [[ "$expected" != "$actual" ]]; then
  echo "checksum mismatch; refusing to restore" >&2
  exit 1
fi

# Archive integrity check before any database write.
pg_restore --list "$dump_file" >/dev/null

dump_url="${PG_DUMP_URL:-${DATABASE_URL:-}}"
if [[ -n "$dump_url" ]]; then
  dump_url="${dump_url/postgresql+asyncpg/postgresql}"
  dump_url="${dump_url/postgresql+psycopg/postgresql}"
  table_count="$(psql "$dump_url" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name <> 'alembic_version'")"
else
  root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  table_count="$(
    cd "$root_dir"
    docker compose exec -T postgres psql -tAc \
      "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name <> 'alembic_version'" \
      --username "${POSTGRES_USER:-slotwise}" --dbname "${POSTGRES_DB:-slotwise}"
  )"
fi

table_count="${table_count//[[:space:]]/}"
if [[ "$table_count" != "0" && "$force" != "--force" ]]; then
  echo "target schema is not empty (${table_count} tables); re-run with --force" >&2
  exit 1
fi

restore_args=(--no-owner --no-privileges --single-transaction)
if [[ "$force" == "--force" ]]; then
  restore_args+=(--clean --if-exists)
fi

if [[ -n "$dump_url" ]]; then
  pg_restore "${restore_args[@]}" --dbname "$dump_url" "$dump_file"
else
  (
    cd "$root_dir"
    docker compose exec -T postgres pg_restore "${restore_args[@]}" \
      --username "${POSTGRES_USER:-slotwise}" \
      --dbname "${POSTGRES_DB:-slotwise}" < "$dump_file"
  )
fi

echo "restore completed: $dump_file"
