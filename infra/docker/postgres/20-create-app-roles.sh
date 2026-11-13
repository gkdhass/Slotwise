#!/bin/sh
# Creates the least-privilege runtime role and the DDL-capable migration role.
# Runs only on a fresh PostgreSQL data volume. Passwords come from the Compose
# environment; none are baked into this file.

set -eu

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  -v mig_user="${MIGRATION_DB_USER:-slotwise_migrator}" \
  -v mig_password="${MIGRATION_DB_PASSWORD:-slotwise-migrator-dev-password}" \
  -v app_user="${APP_DB_USER:-slotwise_app}" \
  -v app_password="${APP_DB_PASSWORD:-slotwise-app-dev-password}" <<'SQL'
SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE',
    :'mig_user', :'mig_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'mig_user')
\gexec

SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE',
    :'app_user', :'app_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')
\gexec

-- The migration role owns the operational schema. The application role gets
-- only DML grants, applied by the Phase 2 migration.
SELECT format('ALTER DATABASE %I OWNER TO %I', current_database(), :'mig_user')
\gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_user')
\gexec

SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'app_user')
\gexec
SQL
