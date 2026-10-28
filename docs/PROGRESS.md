# Slotwise — Progress

Last updated: 2026-10-28 (M6 complete on branch `m6-testing`; GATE 4 pending).

## Current milestone

M6 "test & bug-fix" is **complete** on `m6-testing` and awaiting GATE 4 review.
M7 and Phase 11 are **not** started and will not start without explicit
authorisation.

Full evidence, commands, counts and caveats: **`docs/TEST_REPORT.md`**.

## Milestones

| Milestone | Status | Notes |
|---|---|---|
| Phase 0 — Analysis & setup | Complete | Gate 0 approved (D-01, D-07) |
| M0 Shell | Complete | S01–S11 routes, design tokens, primitives |
| M1 Vertical slice (mock) | Complete | tag `v0.1-mock` |
| M2 Must-haves (persistent) | Complete | Prisma + PostgreSQL, auth, events, availability, public booking transaction, outbox worker, concurrency test |
| M3 Should-haves | Complete | management tokens, cancel/reschedule, booking filters |
| M4 UX fixes | Complete | setup guidance, time-zone clarity, conflict recovery, policy preview |
| M5 Backend swap-in | Complete | All screens on the real API; E2E against real API + DB; security suite |
| M6 Test & bug-fix | **Complete, awaiting Gate 4** | Injectable clock, CI, load harness, axe/contrast/keyboard/reflow, observability, privacy, dependency audit — see below |
| M7 Parity & traceability | Not started | |
| M8 Rebrand sweep | Not started | |
| M9 Launch assets | Not started | |
| M10 Deploy | Not started | Hard-blocked on Neon verification (DEV-13) |
| Phase 11 (optional) Booking Abuse Detection | Not started | Gated on Gate 3 + owner saying "start Phase 11" |

## Delivered in M6

1. **Injectable clock** (`apps/api/src/lib/clock.ts`) wired into `public.ts`,
   `manage.ts`, `eventTypes.ts`; `timezone.test.ts` pins `2027-01-01` so time-zone
   assertions stop drifting with the wall clock. 6 unit + 1 integration test.
2. **CI pipeline** (`.github/workflows/ci.yml`): 7 jobs (lint-typecheck incl.
   build, unit, integration, security, concurrency, e2e, audit) on `postgres:16`
   service containers with real migrations + `verify:constraint`. Root scripts
   `test:security`, `prisma:generate`, `db:migrate:deploy` added so CI and a
   developer run the same commands.
3. **Deployment fix**: `apps/api/scripts/bundle.mjs` (esbuild) — `@slotwise/shared`
   ships as TypeScript source, so `node dist/index.js` fails with
   `ERR_UNKNOWN_FILE_EXTENSION`. `start` now runs `dist/server.js` (DEV-15).
4. **NFR-01 load harness** (`scripts/load.mjs`, `pnpm perf`): builds, seeds
   `perf-load-test`, starts the production bundle, measures both read endpoints
   with exact per-request p95, writes `docs/perf/<stamp>.json`. `/slots` was
   optimised from 7.63 → 2.84 ms/call (cached `Intl.DateTimeFormat` +
   `formatToParts`, proven byte-identical across 7,424 labels / 8 zones).
   Result: `/public/:slug` p95 69.3 ms, `/slots` p95 410.6 ms (final run, 20
   connections, closed loop, 20 s after 5 s warm-up).
5. **Accessibility** (`tests/e2e/a11y.spec.ts`): axe (WCAG 2.2 AA tags) on all 11
   screens at 390 and 1440 px, a contrast audit of every rendered text node
   (216 samples @390, 228 @1440, 8 real fg/bg pairs, worst **5.18:1**, zero below
   AA), a keyboard-only core loop, and reflow at 390/768/1024/1440 plus 200 % zoom.
6. **Observability (NFR-05)**: `x-request-id` validate/echo, pino JSON logs with
   mandatory redaction, `/health` (liveness) + `/health/ready` (`SELECT 1`, 503
   when the DB is down), `captureError()` with an optional webhook and
   token-masked paths. 13 unit + 4 integration tests.
7. **Privacy (NFR-04)**: ordered account/invitee deletion CLI (DEV-17),
   `docs/PRIVACY.md` (data inventory, cookies, retention, deletion limits) and
   `docs/DEPLOYMENT.md` (run modes, env names, health, logs, backup/restore).
8. **Dependency security**: Vitest 4, zod 4 and a `deepmerge-ts` override clear
   `pnpm audit --audit-level=high` (was 3 critical + 3 high). DEV-19.

## Test status (all executed 2026-10-28, final code state, no skips)

| Command | Result |
|---|---|
| `pnpm lint` | 0 errors, 0 warnings (3 packages) |
| `pnpm typecheck` | clean (3 packages) |
| `pnpm build` | api bundle 61.9 kB, web 201.28 kB / 62.93 kB gzip |
| `pnpm test:unit` | **38 passed** — shared 8, api 25, web 5 |
| `pnpm test:integration` | **44 passed** (6 files) |
| `pnpm test:security` | **16 passed** |
| `pnpm test:concurrency` | **2 passed** |
| `pnpm test:e2e --retries=0` | **15 passed** (1.9 min) |
| `pnpm audit --audit-level=high` | **PASS** — 0 critical, 0 high, 3 moderate accepted |
| `pnpm verify:neon` | **PASS 6/6** in 68.6 s (local PostgreSQL 18.3) |
| `pnpm perf --autocannon` | **PASS** — p95 69.3 ms / 410.6 ms |

Required Gate 3 test IDs remain present and passing in
`apps/api/tests/integration/flows.test.ts`: F00-H1, F00-E1, F00-N1, F01-H1,
F01-E1, F01-N1, F02-H1, F02-E1, F02-N1, F02-H2, F03-H1, F03-E1, F03-N1, F03-H2.

## Backup / restore rehearsal (executed today)

`pg_dump` 33,588 bytes → `pg_restore --exit-on-error` into a scratch database →
all 7 tables matched row-for-row (users 4, sessions 35, event_types 5,
availability_rules 17, bookings 16, management_tokens 15, outbox_jobs 35),
`bookings_no_host_overlap` + `btree_gist` + `pgcrypto` + 1 migration present, and
the overlap probe passed against the restored copy. Scratch database dropped
afterwards. Procedure: `docs/DEPLOYMENT.md` §6–7.

## Deviations / risks

- **DEV-13 (HARD BLOCKER before M10): Neon verification is still deferred.**
  `DATABASE_URL` in `.env`/`apps/api/.env` is still the local value (host type
  LOCAL, 54 chars, mtime unchanged). Nothing in this milestone touched Neon. The
  owner must paste the Neon direct URL and run `pnpm verify:neon` (6/6) before any
  deploy work.
- **NFR-01 headroom is thin.** `/slots` p95 is 384–415 ms against a 500 ms budget
  on a contended laptop where the load generator and the server share 8 threads
  and the page file is active. One run of the same code measured 1125 ms. The
  verdict is "met, not comfortably met"; re-verify on an idle host before M10
  (DEV-21).
- **No CI execution observed yet.** The 7-job workflow is committed and every
  command in it has been run locally, but the first push will be its first real
  run. CI uses Node 20 + `postgres:16`; this machine is Node 22.16 + PostgreSQL
  18.3. Aligning the Node version is worth doing before M10.
- **DEV-10/DEV-11 stand**: Playwright boots two web servers, and E2E/perf run with
  raised rate limits; the real limits are proven by `tests/security`.
- **Accepted dependency advisories** (below the `high` gate): `uuid < 11.1.1`
  (dev-only) and `react-router` 6 → 7 (major; SPA-only, no SSR). See
  `docs/TEST_REPORT.md` §12.
- **Not covered**: Firefox/WebKit, real mobile devices, PITR/off-host restore,
  test coverage percentage, load on the booking write path.

## Open questions for owner (Gate 4)

1. Accept M6 and authorise M7?
2. Neon direct `DATABASE_URL` so `pnpm verify:neon` can produce Neon results
   (DEV-13) — required before M10, and the only outstanding hard blocker.
3. Should CI run Node 22 (matching development) instead of Node 20?
4. Is ~20 % headroom on NFR-01 acceptable for the MVP, or should `/slots` get a
   further optimisation (e.g. response-window cap or caching) before M7?
