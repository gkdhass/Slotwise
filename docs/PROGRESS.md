# Slotwise — Progress

Last updated: 2026-10-28 (GATE 4 accepted; Gate 4 conditions applied on
`m6-testing`; M7 complete on `m7-parity`, awaiting GATE 5).

## Current milestone

GATE 4 accepted M6. The four conditions attached to that acceptance are
**complete** on `m6-testing`:

1. `/public/:slug/slots` is capped at 31 days (422 + field error), and both web
   call sites clamp to the shared constant (DEV-24).
2. The slots read path loads only the bookings that overlap the window, in one
   query, and generates slots in memory. `EXPLAIN` showed an existing index scan
   and no missing index, so none was added (DEV-25).
3. `pnpm perf` re-run three times on the same profile; all three p95 values are
   published in `docs/TEST_REPORT.md` §9.4 — 184.6 / 212.0 / 210.7 ms.
4. `docs/TEST_REPORT.md` states that every number is local PostgreSQL 18.3 and
   that Neon network latency is excluded and must be re-measured.

CI now runs Node 22 in all seven jobs and the root `package.json` declares
`engines.node >= 22` (DEV-22). The three moderate audit advisories are accepted
with reasoning (DEV-23). **No GitHub Actions run has been observed yet.**

M7 "parity & traceability" is **complete** on `m7-parity` and awaiting GATE 5.
M8, M9, M10 and Phase 11 are **not** started and will not start without explicit
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
| M6 Test & bug-fix | Complete | GATE 4 accepted 2026-10-28; conditions applied on `m6-testing` |
| M7 Parity & traceability | In progress | `m7-parity`: parity score, `docs/TRACEABILITY.md`, gap list, `docs/REPORT_OUTLINE.md`, README clean-clone test |
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

## Delivered in M7 (parity & traceability)

1. **`docs/PARITY.md`** — the requirement register for all 10 FRs and 6 NFRs with
   priority weights (must 3 / should 2 / could 1), pass/partial/fail scores with
   evidence links, the arithmetic shown (39.0 / 44 = **88.6 %**) and the verdict
   rule applied. Two musts and one should are scored **partial**, and FR-10 is
   scored **fail** by decision — nothing is rounded up.
2. **`docs/TRACEABILITY.md`** — all 16 rows of the Implementation Plan's
   traceability matrix (row 16, the M8 rebrand, is the only undelivered row) plus
   a requirement → evidence table and a screen → route table, with real file
   paths, route mounts and test names.
3. **`docs/GAPS.md`** — 15 open gaps, each with severity, a fix plan or a reasoned
   deferral and the owner action where one is needed. Six gaps were cheap and
   were fixed in this milestone (archive path, booking-list filters, range-cap
   boundary, windowed-booking query, README, S07 stale-slot race).
4. **`docs/REPORT_OUTLINE.md`** — chapter-by-chapter mapping of artefacts to the
   final report, the six figures that must be drawn by hand, and what the owner
   must write (chiefly the literature review and the reflective chapters).
5. **`docs/README_CHECK.md`** — a clean clone in a temp folder, timed. First
   attempt **failed** at `pnpm db:migrate` (`Environment variable not found:
   DATABASE_URL`, because the API reads `apps/api/.env`); with the fix, 4 min 33 s
   to a working database and `pnpm dev` serving web + api. The README was
   rewritten accordingly.
6. **S07 stale-slot race fixed** (DEV-28). One intermittent E2E failure
   (`toHaveAttribute("aria-pressed", "true")`) was traced to the product, not the
   test: on a date change the previous day's slot buttons stayed clickable until
   the new list arrived, so a click could select a slot that then vanished while
   "Continue" stayed enabled. The screen now clears the list and the selection
   whenever the `(slug, date, zone)` query changes, and a new E2E test pins it.

## Test status (all executed 2026-10-28, final code state, no skips)


| Command | Result |
|---|---|
| `pnpm lint` | 0 errors, 0 warnings (3 packages) |
| `pnpm typecheck` | clean (3 packages) |
| `pnpm build` | web 201.34 kB / 62.95 kB gzip; api bundle 62.9 kB |
| `pnpm test:unit` | **40 passed** — shared 10, api 25, web 5 |
| `pnpm test:integration` | **48 passed** (6 files) |
| `pnpm test:security` | **16 passed** |
| `pnpm test:concurrency` | **2 passed** |
| `pnpm test:e2e --retries=0` | **16 passed** (2.0-2.2 min, three consecutive runs) |
| `pnpm audit --audit-level=high` | **PASS** — 0 critical, 0 high, 3 moderate accepted (DEV-23) |
| `pnpm verify:neon` | **PASS 6/6** in 68.6 s — run against **local PostgreSQL 18.3**, not Neon |
| `pnpm perf --autocannon` | **PASS** ×3 — `/slots` p95 184.6 / 212.0 / 210.7 ms; `/public/:slug` p95 59.5 / 61.7 / 65.9 ms |

122 automated tests total (40 + 48 + 16 + 2 + 16). Required Gate 3 test IDs remain
present and passing in `apps/api/tests/integration/flows.test.ts`: F00-H1, F00-E1,
F00-N1, F01-H1, F01-E1, F01-N1, F02-H1, F02-E1, F02-N1, F02-H2, F03-H1, F03-E1,
F03-N1, F03-H2, plus F01-H2 (archive), F01-E2 (31-day cap), F02-H3 (windowed
booking query) and F03-H3 (booking-list filters).

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
- **NFR-01 now has real headroom.** `/slots` p95 is 184.6–212.0 ms against a
  500 ms budget (37–42 %) after the Gate 4 optimisation, up from 384–415 ms
  (DEV-24, DEV-25, `docs/TEST_REPORT.md` §9.2/§9.4). **These are loopback numbers
  against local PostgreSQL 18.3 — Neon network latency is not included and
  NFR-01 must be re-measured after Neon is connected.**
- **No CI execution observed yet.** The 7-job workflow is committed and every
  command in it has been run locally, but the first push will be its first real
  run. CI now runs Node 22 (DEV-22) like this machine; the remaining difference is
  `postgres:16` in CI vs PostgreSQL 18.3 here.
- **DEV-10/DEV-11 stand**: Playwright boots two web servers, and E2E/perf run with
  raised rate limits; the real limits are proven by `tests/security`.
- **Accepted dependency advisories** (below the `high` gate, DEV-23): `uuid <
  11.1.1` (dev-only) and `react-router` 6 → 7 (major; SPA-only, no SSR). See
  `docs/TEST_REPORT.md` §12.
- **Not covered**: Firefox/WebKit, real mobile devices, PITR/off-host restore,
  test coverage percentage, load on the booking write path.

## Open questions for owner (Gate 5)

1. Accept M7 (parity score, traceability, gap list, report outline) and authorise
   M8?
2. Paste the first GitHub Actions run result so CI can be called green or fixed.
3. Neon direct `DATABASE_URL` so `pnpm verify:neon` can produce Neon results
   (DEV-13) — required before M10, and the only outstanding hard blocker.
