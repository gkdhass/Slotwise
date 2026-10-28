# DEPLOYMENT.md — running, health-checking, backing up and restoring Slotwise

Scope: the single-host MVP described in `docs/00_ANALYSIS.md`. Hosting follows
**D-07** (web on Vercel, API + outbox worker on a long-running Node host such as
Render or Railway, PostgreSQL per **D-01**). Payments are disabled (**D-08**).

Everything below was executed on this machine (Windows 11, PostgreSQL 18.3,
Node 22.16.0) except where a step is explicitly marked **not yet performed**.

---

## 1. What runs

| Process | Command | Notes |
| --- | --- | --- |
| Web (static SPA) | `pnpm --filter @slotwise/web build` → serve `apps/web/dist` | Vite build; needs `VITE_API_BASE_URL` at build time |
| API | `pnpm --filter @slotwise/api build` then `pnpm --filter @slotwise/api start` | `start` = `node dist/server.js`, a compiled bundle |
| Outbox worker | `pnpm --filter @slotwise/api worker:email` | Polls `outbox_jobs` with `FOR UPDATE SKIP LOCKED` |
| Outbox via HTTP | `POST /api/v1/worker/run-outbox` with `x-worker-secret` | Alternative to the separate process, so the host stays reversible (D-07) |
| Database | PostgreSQL 16+ | Needs `pgcrypto` and `btree_gist`; the migration creates both |

The API must **not** be deployed to a serverless platform: it holds a Prisma
connection pool and the worker depends on `SKIP LOCKED` polling (D-07).

### Why `start` runs `dist/server.js`, not `dist/index.js`

`@slotwise/shared` is published as TypeScript source so Vite, `tsx` and Vitest
consume it with no build step. Plain `node dist/index.js` therefore fails with
`ERR_UNKNOWN_FILE_EXTENSION`. `pnpm build` runs `tsc -b` (type-check plus
declarations/source maps) and then `apps/api/scripts/bundle.mjs` (esbuild),
which inlines the workspace package and leaves npm dependencies external.
Measured: `dist/server.js` = 104.4 kB, boots under `NODE_ENV=production`, and
`GET /health` returns `{"status":"ok","service":"slotwise-api"}`.

---

## 2. Environment variables

Names only — never commit values. `.env.example` lists the same names.

| Variable | Required in production | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | yes | PostgreSQL connection string. Use the **direct** (non-pooled) URL for migrations. |
| `SESSION_SECRET` | yes, ≥ 16 chars | Session cookie signing/derivation. Startup refuses to run without it. |
| `CSRF_SECRET` | yes | Double-submit CSRF token secret. |
| `APP_BASE_URL` | yes | Absolute base URL used in emails and manage links. |
| `EMAIL_PROVIDER` | yes (`resend`) | `console` is the dev transport and logs email content. |
| `RESEND_API_KEY`, `EMAIL_FROM` | when `EMAIL_PROVIDER=resend` | Delivery. |
| `WORKER_SECRET` | yes if the HTTP worker route is exposed | Authenticates `POST /api/v1/worker/run-outbox`. |
| `PORT` | no (default 4000) | Listen port. |
| `LOG_LEVEL` | no (default `info`) | `debug`/`info`/`warn`/`error`/`silent`. |
| `ERROR_MONITOR_WEBHOOK_URL` | no | JSON POST target for unhandled errors. |
| `OUTBOX_MAX_ATTEMPTS`, `OUTBOX_BACKOFF_BASE_MS` | no | Retry policy. |
| `RATE_LIMIT_*` | no | Overrides for the fixed-window limits. |
| `VITE_API_BASE_URL` | web build | API origin baked into the SPA bundle. |

**Startup guard** (`apps/api/src/lib/config.ts`): with `NODE_ENV=production` the
process refuses to start if `CSRF_DISABLED=true`, if `SESSION_SECRET` is missing
or shorter than 16 characters, or if `DATABASE_URL` is unset. This is proven by
`apps/api/tests/security/security.test.ts`.

---

## 3. Release procedure

```bash
pnpm install --frozen-lockfile
pnpm --filter @slotwise/api prisma:generate
pnpm build                 # web dist + api dist/server.js
pnpm --filter @slotwise/api prisma:migrate:deploy   # production: deploy, never dev
```

Then start the API (`node dist/server.js`), the worker, and serve the web build.
`prisma migrate dev` is a developer command: it can reset the database and must
never be run against production.

Release checklist:

1. `pnpm lint`, `pnpm typecheck`, `pnpm build` clean.
2. `pnpm db:migrate:deploy` applied (the migration is additive; see §7).
3. `GET /health` returns 200 and `GET /health/ready` returns 200.
4. One manual booking through the public page, then cancel it.
5. Worker running: a queued email leaves `pending` within one poll interval.

---

## 4. Health and readiness

| Endpoint | Checks | Failure mode |
| --- | --- | --- |
| `GET /health` | Process is up. Does **not** touch the database. | Use for liveness; a restart will not fix a slow query. |
| `GET /health/ready` | `SELECT 1` against PostgreSQL. | Returns **503** `{"status":"unavailable","database":"unreachable"}` so a load balancer takes the instance out. |
| `GET /api/v1/health` | Backwards-compatible `{"status":"ok"}`. | — |

```bash
curl -sS https://<api-host>/health
# {"status":"ok","service":"slotwise-api","version":"0.0.0"}
curl -sS -o /dev/null -w '%{http_code}\n' https://<api-host>/health/ready
# 200
```

Point the platform's liveness probe at `/health` and its readiness probe at
`/health/ready`. Health probes are excluded from request logging so they cannot
flood the log.

---

## 5. Logs, request ids and error monitoring (NFR-05)

- Every request gets an id: an inbound `x-request-id` is kept if it matches
  `^[A-Za-z0-9._:-]{8,128}$`, otherwise a UUID is generated. The id is returned
  in the `x-request-id` response header and inside every error envelope
  (`error.requestId`), so a user's screenshot identifies one log line.
- Logs are JSON (pino): `level`, `time`, `service`, `req.id`, method, url,
  status, `responseTime`.
- **Redaction is mandatory**: `authorization`, `cookie`, `x-csrf-token`,
  `x-worker-secret`, `set-cookie`, and any `password`/`token` field are replaced
  with `[Redacted]`. Proven by `apps/api/src/lib/logger.test.ts`.
- Unhandled errors go through `captureError()`: one structured `error` line, plus
  an optional JSON POST to `ERROR_MONITOR_WEBHOOK_URL` (2 s timeout,
  fire-and-forget, never blocks or fails the response). The payload contains the
  request id, method, status, error name/message/stack and the path **with
  management tokens masked**; no body, cookie, header or query string is sent.
  Proven by `apps/api/src/lib/errorMonitor.test.ts`.
- Under `NODE_ENV=test` the logger is silent so a failing assertion is visible.

Not implemented: no metrics/tracing exporter, no dashboards, no alert rules. The
webhook hook is the integration point for whichever tracker the owner picks.

---

## 6. Backup

Logical backups with `pg_dump` in custom format (compressed, restorable
selectively, and safe to take while the API is serving):

```bash
pg_dump --dbname="$DATABASE_URL" --format=custom --no-owner --no-privileges \
        --file=slotwise-$(date -u +%Y%m%dT%H%M%SZ).dump
```

- Run daily; keep 7 daily dumps plus the last dump before every release.
- Store off the database host (object storage), encrypted at rest.
- Verify the dump is non-empty and restorable (§7) — an unverified backup is not
  a backup.
- The dump contains personal data (host email + Argon2id hash, invitee name,
  email, optional note, time zone). Treat it as confidential, and see
  `docs/PRIVACY.md` for the retention consequence.

### Measured rehearsal (2026-10-28, local PostgreSQL 18.3)

| Step | Result |
| --- | --- |
| `pg_dump --format=custom` | exit 0, 32,537 bytes |
| `CREATE DATABASE slotwise_restore_check` | exit 0 |
| `pg_restore --no-owner --no-privileges --exit-on-error` | exit 0 |
| Row counts, source vs restored | `users` 4/4, `sessions` 26/26, `event_types` 5/5, `availability_rules` 17/17, `bookings` 16/16, `management_tokens` 15/15, `outbox_jobs` 31/31 — all OK |
| Schema objects | `bookings_no_host_overlap / x` (EXCLUDE) present, `btree_gist` + `pgcrypto` present, 1 migration recorded in `_prisma_migrations` |
| Overlap probe in the restored copy | `PASS: 23P01 overlap rejected by bookings_no_host_overlap`; exactly 1 of the 2 conflicting rows kept |

The probe inserts a user, an event type and two overlapping bookings inside a
`DO` block; the second insert must raise `exclusion_violation`. If the constraint
were lost in the restore, the block raises `OVERLAP ACCEPTED` and the rehearsal
fails loudly.

---

## 7. Restore

Restore into a **scratch** database first, verify, then promote. Never restore
directly over a live database: a partial restore plus a running API is worse than
downtime.

```bash
# 1. stop the API and the worker (or put the host in maintenance mode)
# 2. restore into a new database
createdb slotwise_restore
pg_restore --dbname=slotwise_restore --no-owner --no-privileges --exit-on-error slotwise-<stamp>.dump

# 3. verify: row counts, extensions, constraint
psql --dbname=slotwise_restore -c "select count(*) from bookings"
psql --dbname=slotwise_restore -c "select conname from pg_constraint where conname = 'bookings_no_host_overlap'"
psql --dbname=slotwise_restore -c "select extname from pg_extension where extname in ('pgcrypto','btree_gist')"
psql --dbname=slotwise_restore -c "select count(*) from _prisma_migrations where finished_at is not null"

# 4. prove the no-double-booking invariant, not just the row count
#    (run the DO block from §6's probe)
# 5. point DATABASE_URL at the restored database, start the API, check /health/ready
# 6. one manual booking + cancel
```

Rollback of a bad release is a redeploy of the previous bundle. Rollback of a bad
migration is a restore: migrations are additive, so no down-migration is provided.

**Not yet performed:** restoring from an off-host/cloud backup, and a
point-in-time recovery (PITR) drill. This MVP takes logical dumps only; PITR needs
WAL archiving, which the chosen host must enable if the owner wants it.

---

## 8. Operational limits of this MVP

- Single API instance assumed: the rate limiter is in-process (`Map`), so N
  instances multiply the effective limit. Move to a shared store before scaling out.
- The worker is a polling loop; two workers are safe (`SKIP LOCKED`) but untested
  beyond one.
- No autoscaling, no CDN configuration, no WAF, no metrics backend.
- `DEV-13`: the Neon database has not been exercised. All results in this repo
  come from local PostgreSQL 18.3 and CI's `postgres:16` service container. A full
  `pnpm verify:neon` run is a hard requirement before the first deploy.
