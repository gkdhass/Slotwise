# Slotwise

Focused single-host scheduling MVP (final-year project). Clean-room
implementation; not affiliated with any third-party scheduling product.

One host publishes an event type with weekly availability, a visitor picks a
server-generated slot and books without an account, and both sides can cancel or
reschedule through a bearer-token management link. Confirmation email is queued in
the same transaction that creates the booking and sent by an outbox worker.

## Status

M7 (parity & traceability). Gates 0–4 approved; M8–M10 and Phase 11 are not
started. What exists, what is tested and what is still open:

| Document | Contents |
| --- | --- |
| `docs/PROGRESS.md` | milestone state, test counts, risks, open questions |
| `docs/TEST_REPORT.md` | every suite, command, count and caveat (NFR-01 performance) |
| `docs/PARITY.md` | requirement register, weighted score (88.6 %) and verdict |
| `docs/TRACEABILITY.md` | feature → screen → flow → table → route → milestone → test |
| `docs/GAPS.md` | every gap with a fix plan or a reasoned deferral |
| `docs/DECISIONS.md` | decisions and deviations (D-xx, DEV-xx) |
| `docs/REPORT_OUTLINE.md` | how these artefacts map to the final report |
| `docs/DEPLOYMENT.md`, `docs/PRIVACY.md` | run modes, health, backup/restore; data and retention |

## Stack

- Frontend: React + Vite + Tailwind CSS (`apps/web`), SPA on port **5173**
- Backend: Node.js + Express + TypeScript (`apps/api`), API on port **4000**
- Database: PostgreSQL + Prisma (`apps/api/prisma`)
- Shared: `packages/shared` (slot generation, label formatting, constants)
- Workspaces: pnpm 12

## Prerequisites

- Node.js **>= 22** (`engines` in `package.json`; CI uses 22)
- pnpm 12 (`npm i -g pnpm`)
- PostgreSQL **16 or newer**, reachable from your machine. Either:
  - Docker: `docker compose up -d` (see `docker-compose.yml`), or
  - a native install, or
  - a Neon dev branch (use the **direct**, non-pooled connection string).

## Setup (target: under 10 minutes)

```bash
git clone <repo-url> slotwise
cd slotwise
pnpm install
```

1. **Create the database** (skip if your provider already made one):

   ```bash
   createdb -U postgres slotwise        # or: docker compose up -d
   ```

2. **Create both env files.** The API and Prisma read `apps/api/.env`; the root
   `.env` is for tooling. Keep the two `DATABASE_URL` values identical.

   ```bash
   cp .env.example .env
   cp .env.example apps/api/.env
   ```

   Fill at least `DATABASE_URL`, `SESSION_SECRET`, `CSRF_SECRET` and
   `WORKER_SECRET` in **both** files. Any long random string works locally
   (`openssl rand -hex 32`). `.env` files are git-ignored; `.env.example` holds
   names only.

3. **Enable the extensions** the schema needs:

   ```bash
   psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS pgcrypto; CREATE EXTENSION IF NOT EXISTS btree_gist;"
   ```

4. **Migrate** (creates the 7 tables plus the `bookings_no_host_overlap`
   exclusion constraint):

   ```bash
   pnpm db:migrate:deploy      # CI/production; applies committed migrations
   # or, while developing the schema:
   pnpm db:migrate
   ```

5. **Run it**:

   ```bash
   pnpm dev                    # web on http://127.0.0.1:5173, api on http://localhost:4000
   ```

   Check `http://localhost:4000/health` (liveness) and
   `http://localhost:4000/health/ready` (database reachable). Register an owner at
   `/register`, then create → set availability → publish an event.

6. **Optional demo data** for the browser suites:

   ```bash
   pnpm --filter @slotwise/api seed:e2e     # owner e2e.owner@slotwise.test / e2e-password-123
   pnpm --filter @slotwise/api seed:perf    # perf-load-test fixture for the load harness
   ```

Measured on a clean clone (Windows 11, warm pnpm store): clone 2 s, install
4 min 4 s, migrate 19 s — **4 min 33 s to a working database**, plus a few
seconds for `pnpm dev`. Details and everything that broke on the first attempt:
`docs/README_CHECK.md`.

## Tests

The suites need a migrated database and the env files from step 2.

```bash
pnpm lint                     # eslint, 3 packages
pnpm typecheck                # tsc -b --noEmit, 3 packages
pnpm build                    # web + api (esbuild bundle)
pnpm test:unit                # 40  (shared 10, api 25, web 5) — no database
pnpm test:integration         # 48  (real PostgreSQL, real migrations)
pnpm test:security            # 16  (CSRF enforced, rate limits, headers, prod guard)
pnpm test:concurrency         # 2   (50 parallel bookings → exactly one)
pnpm test:e2e --retries=0     # 16  (Playwright, Chromium; seeds its own fixtures)
pnpm audit --audit-level=high # 0 critical, 0 high
pnpm verify:neon              # 6-step database verification (target, migrate, constraint, 3 suites)
pnpm perf --autocannon        # NFR-01 load profile, writes docs/perf/<stamp>.json
```

Notes:

- Integration/security/concurrency run with `CSRF_DISABLED=true` and raised rate
  limits so each test owns the database; the security suite is the one place the
  real CSRF and rate-limit behaviour is proven.
- `pnpm test:e2e` starts both servers itself (`playwright.config.ts`) and needs
  the Playwright browsers once: `pnpm exec playwright install chromium`.
- `pnpm verify:neon` prints only the host type and value length — never the
  connection string. Against a local database it proves the migrations and the
  constraint, not Neon.

## Layout

```
apps/api        Express API, Prisma schema + migrations, outbox worker, ops scripts
apps/web        React SPA (S01–S11 screens), API client, design tokens
packages/shared slot generation, label formatting, shared constants
tests/e2e       Playwright: core loop, public pages, accessibility
docs            analysis, decisions, test report, parity, traceability, gaps, deployment, privacy
docs/perf       load-harness artefacts (JSON, one per run)
docs/a11y       axe and contrast artefacts per viewport
```

## Known limitations

Single host only; no teams, calendar sync, payments (D-08) or SMS. Neon
verification is outstanding (DEV-13, required before M10), CI has not yet run on
GitHub, and NFR-02/NFR-04 are partly proven — see `docs/GAPS.md` for the full list
with fix plans.

## License

TBD (project). No third-party code copied.
