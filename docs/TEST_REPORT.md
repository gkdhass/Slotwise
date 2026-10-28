# TEST_REPORT.md — M6 (test & bug-fix)

Scope: the M6 gate. Everything below was **executed on 2026-10-28** on the
development machine against a real PostgreSQL database, with the real API and the
real SPA. No test is skipped, no assertion is disabled, and no suite is mocked
except where a unit test deliberately isolates a module (stated in place).

What this report does **not** claim: that GitHub Actions has run the committed
pipeline (no CI execution has been observed yet — see §10), or that anything has
been verified on Neon (DEV-13 — see §11).

---

## 1. Environment (measured, not assumed)

| Item | Value |
| --- | --- |
| OS | Windows 11, build 10.0.26300 (`win32 x64`) |
| CPU / RAM | 12th Gen Intel Core i3-1215U, 8 logical cores / 7.7 GB |
| Node | v22.16.0 |
| pnpm | 12.15.0 |
| Database | local PostgreSQL **18.3** (`x86_64-windows`), host type **LOCAL** |
| Browser (E2E) | Chromium via Playwright (headless), 1 worker |
| Test runner | Vitest 4.1.12 (unit/integration/security/concurrency), Playwright 1.5x (E2E) |

The machine was **not idle** during these runs: a browser, an editor and this
agent were resident, and the OS commit charge (19.9 GB) far exceeds physical RAM
(7.7 GB), so the page file was in use. That matters only for §9 (performance) and
is quantified there. Every other suite is latency-insensitive.

Connection strings are never printed. The database target check
(`node scripts/check-db-target.mjs`) reports host type, file size, mtime and value
length only.

---

## 2. Results summary

All commands are the root `package.json` scripts, run from the repository root.

| Suite | Command | Files | Tests | Result |
| --- | --- | --- | --- | --- |
| Lint | `pnpm lint` | 3 packages | — | **PASS** (0 errors, 0 warnings) |
| Typecheck | `pnpm typecheck` | 3 packages | — | **PASS** |
| Build | `pnpm build` | web + api | — | **PASS** (api bundle 61.9 kB, web 201.28 kB / 62.93 kB gzip) |
| Unit | `pnpm test:unit` | 8 | **38** | **PASS** (shared 8, api 25, web 5) |
| Integration | `pnpm test:integration` | 6 | **44** | **PASS** |
| Security | `pnpm test:security` | 1 | **16** | **PASS** |
| Concurrency | `pnpm test:concurrency` | 1 | **2** | **PASS** |
| E2E | `pnpm test:e2e --retries=0` | 4 | **15** | **PASS** (1.9 min) |
| Dependency audit | `pnpm audit --audit-level=high` | — | — | **PASS** (0 critical, 0 high; 3 moderate accepted, §12) |
| Database verification | `pnpm verify:neon` | — | 6 steps | **PASS** 6/6 in 68.6 s |
| Performance | `pnpm perf --autocannon` | — | 2 endpoints | **PASS** (§9) |

`--retries=0` is used for the E2E run on purpose: a green run must be a first-try
green run. (CI keeps Playwright's `retries=1` and uploads traces on failure.)

Total: **115 automated tests** (38 + 44 + 16 + 2 + 15), all passing, plus the
six-step database verification and the load harness.

---

## 3. Requirement traceability

IDs come from `docs/00_ANALYSIS.md`. "Where" is the file that proves it.

| ID | Requirement | Where | Result |
| --- | --- | --- | --- |
| FR-01 | Owner registers, verifies email, logs in/out | `apps/api/tests/integration/auth.test.ts` (7), `tests/e2e/public.spec.ts` "S01 signs in…", "S01 rejects wrong credentials" | PASS |
| FR-02 | Create/edit/archive event type | `flows.test.ts` F01-H1/E1/N1, `tests/e2e/core-loop.spec.ts` "S02 → S05" | PASS |
| FR-03 | Weekly availability + time zone | `flows.test.ts` F02-H1/E1/N1/H2, `timezone.test.ts` (7) | PASS |
| FR-04 | Visitor views published event and slots | `flows.test.ts` F03-H1/E1/N1/H2, `public.spec.ts` "S06 shows the published event…", "S07 lists real slots…" | PASS |
| FR-05 | Visitor books without an account | `flows.test.ts` F03-*, `core-loop.spec.ts` "S06 → S09 → S10" | PASS |
| FR-06 | No overlapping confirmed bookings per host | `tests/concurrency/booking.test.ts` (2), `verify:constraint` (5 checks), restored-copy probe (§8) | PASS |
| FR-07 | Confirmation email queued, only after commit | `tests/integration/outbox.test.ts` (5) | PASS |
| FR-08 | Cancel/reschedule via secure token | `flows.test.ts` F02-H2, `core-loop.spec.ts` "S10 reschedule…", `public.spec.ts` "S10 shows a generic denial…" | PASS |
| FR-09 | Clear setup/conflict messages | `core-loop.spec.ts` "a taken slot returns to slot selection…", `apps/web/src/App.test.tsx` (5) | PASS |
| FR-10 | Paid bookings | not built (D-08) | N/A by decision |
| NFR-01 | Read API p95 < 500 ms | `scripts/load.mjs`, `docs/perf/*.json` | PASS with caveats (§9) |
| NFR-02 | WCAG 2.2 AA, keyboard core loop, axe clean | `tests/e2e/a11y.spec.ts`, `docs/a11y/contrast-390.json`, `contrast-1440.json` | PASS (§7) |
| NFR-03 | Zero double bookings | concurrency suite + exclusion constraint probe | PASS |
| NFR-04 | Minimal invitee data, retention, deletion path | `accountDeletion.test.ts` (7), `docs/PRIVACY.md` | PASS |
| NFR-05 | Structured logs, request ids, `/health`, monitor hook | `logger.test.ts` (5), `requestId.test.ts` (5), `errorMonitor.test.ts` (7), `health.test.ts` (2), `observability.test.ts` (4) | PASS |
| NFR-06 | Verified at 390 px and 1440 px (also 768/1024) | `a11y.spec.ts` axe scans + reflow test | PASS |

Required test IDs from the Gate 3 list (all in `flows.test.ts`, all passing):
F00-H1, F00-E1, F00-N1, F01-H1, F01-E1, F01-N1, F02-H1, F02-E1, F02-N1, F02-H2,
F03-H1, F03-E1, F03-N1, F03-H2.

---

## 4. Unit tests — 38

| File | Tests | What it pins |
| --- | --- | --- |
| `packages/shared/src/slots.test.ts` | 7 | Slot generation: grid alignment, DST spring-forward/fall-back, min notice, horizon, cancelled/free slots, label formatting |
| `packages/shared/src/index.test.ts` | 1 | Shared exports/constants |
| `apps/api/src/lib/clock.test.ts` | 6 | Injectable clock: default is real time, `setClock`/`resetClock`, `now()` monotonic use in slots, restore on reset |
| `apps/api/src/lib/logger.test.ts` | 5 | JSON shape, `req.id`, redaction of `authorization`/`cookie`/`x-csrf-token`/`x-worker-secret`/`set-cookie`/`password`/`token`, silence under `NODE_ENV=test` |
| `apps/api/src/lib/errorMonitor.test.ts` | 7 | No-op without a webhook, payload shape, management-token masking in the path, 2 s timeout, never throws, never blocks, no body/headers/query leaked |
| `apps/api/src/middleware/requestId.test.ts` | 5 | Inbound id kept when it matches `^[A-Za-z0-9._:-]{8,128}$`, regenerated otherwise, echoed in the response header, present in error envelopes |
| `apps/api/src/health.test.ts` | 2 | `/health` liveness (no DB), `/health/ready` semantics |
| `apps/web/src/App.test.tsx` | 5 | Routing, S01 validation, S05 policy preview, S06 policy text, API-client contract |

Unit tests never touch the database (`GET /api/v1/bookings` returns 401 from
`requireAuth` before any query; `getSessionUser(undefined)` returns `null` without
a query). Verified by running the suite with no database connection available.

### Injectable clock (M6 task 1)

`apps/api/src/lib/clock.ts` exposes `now()`; `public.ts`, `manage.ts` and
`eventTypes.ts` use it instead of `new Date()`. `timezone.test.ts` pins the clock
to `2027-01-01` and asserts the API's slot window, min-notice and past-slot
filtering all move with it. Without the clock these assertions would drift with
the wall clock and start failing in January 2027.

---

## 5. Integration tests — 44 (real PostgreSQL, real migrations, no mocks)

| File | Tests | Coverage |
| --- | --- | --- |
| `flows.test.ts` | 14 | The Gate 3 ID list: happy/error/negative for auth, event types, availability and public booking |
| `auth.test.ts` | 7 | Register → verify → login → logout, session revocation, duplicate email, weak password, unverified login refused, reset flow |
| `timezone.test.ts` | 7 | DST spring-forward/fall-back, host≠invitee zones, pinned-clock window, invalid zone → 422 |
| `outbox.test.ts` | 5 | Job exists only if the booking transaction committed; retry with exponential backoff; bounded attempts; `FOR UPDATE SKIP LOCKED` polling |
| `observability.test.ts` | 4 | `x-request-id` echo/generation, `/health/ready` 200 and 503 (database unreachable), error envelope carries `requestId` |
| `accountDeletion.test.ts` | 7 | Host deletion order (bookings → tokens → sessions → rules → events → user), invitee-only deletion, dry-run, idempotent re-run, no orphan rows |

Run with `fileParallelism: false`, `CSRF_DISABLED=true` and raised rate limits, so
each test owns the database. `purgeUsers` deletes bookings before users because
`Booking.user`/`Booking.eventType` are `onDelete: Restrict` on purpose (DEV-17).

---

## 6. Security & concurrency — 16 + 2

`tests/security/security.test.ts` (16): rate limits → 429 per bucket, `helmet`
headers incl. `Referrer-Policy: no-referrer`, CORS exact allow-list (allowed
origin only, no wildcard, credentials), CSRF genuinely enforced on every
state-changing auth route (`vitest.security.config.ts`, real double-submit),
`GET /api/v1/auth/csrf` bootstrap, manage route `no-store` + `no-referrer`,
production startup guard (refuses to boot with `CSRF_DISABLED=true`, short/missing
`SESSION_SECRET`, or missing `DATABASE_URL`), and no token/password in any
response body.

`tests/concurrency/booking.test.ts` (2):

- 50 parallel booking requests for the same slot → exactly one `confirmed`, the
  rest `409 SLOT_UNAVAILABLE`.
- Overlapping slots across two event types for the same host → at most one
  confirmed booking (the constraint is per host, not per event type).

The expected `23P01` rejections are logged by Prisma during these tests; that
output is the proof the database, not the application, is enforcing the invariant.

---

## 7. Accessibility — axe, contrast, keyboard, zoom, reflow

`tests/e2e/a11y.spec.ts` (4 test instances, all passing):

1. **axe + contrast at 390 px** — 11 screens, tags `wcag2a`, `wcag2aa`,
   `wcag21a`, `wcag21aa`, `wcag22aa`.
2. **axe + contrast at 1440 px** — same 11 screens.
3. **Keyboard-only core loop** — sign in, publish path, book, manage, cancel using
   only `Tab`/`Shift+Tab`/`Enter`/`Space`/typing. Every step asserts the focused
   element before activating it.
4. **Reflow** — no horizontal overflow at 390, 768, 1024, 1440 and at 640×360
   (200 % zoom of a 1280×720 window, WCAG 1.4.10).

Screens scanned: S01 sign in, S02 dashboard, S03 event editor, S04 availability,
S05 preview and publish, S06 public event, S07 slot selector, S08 invitee details,
S09 confirmation, S10 manage booking, S11 booking list.

### Contrast audit (not just axe)

axe's contrast rule skips text over gradients, images and translucent layers. The
suite therefore walks every text node, composites `color` alpha over the nearest
opaque ancestor background, and applies the WCAG threshold per text size: **4.5:1**
normal, **3:1** large (≥ 24 px, or ≥ 18.66 px bold).

| Viewport | Samples | Screens | Distinct fg/bg pairs | Below AA | Worst pair |
| --- | --- | --- | --- | --- | --- |
| 390 px | 216 | 11 | 8 | **0** | 5.18:1 — `rgb(22,121,75)` on `rgb(240,253,244)` ("confirmed"/"published" badge) |
| 1440 px | 228 | 11 | 8 | **0** | 5.18:1 — same pair |

The eight real pairs, worst first:

| Ratio | Samples | Pair |
| --- | --- | --- |
| 5.18 | 7 | `rgb(22,121,75)` on `rgb(240,253,244)` — success badge |
| 5.93 | 16 | `rgb(83,97,118)` on `rgb(247,248,252)` — muted text on page background |
| 6.29 | 48 | `rgb(83,97,118)` on `rgb(255,255,255)` — muted text on cards |
| 6.51 | 1 | `rgb(255,255,255)` on `rgb(180,35,50)` — destructive button |
| 6.52 | 11 | `rgb(255,255,255)` on `rgb(98,70,199)` — primary button |
| 6.52 | 6 | `rgb(98,70,199)` on `rgb(255,255,255)` — primary link |
| 15.33 | 14 | `rgb(23,32,51)` on `rgb(247,248,252)` — headings on page background |
| 16.27 | 113 | `rgb(23,32,51)` on `rgb(255,255,255)` — body text |

Artifacts: `docs/a11y/contrast-390.json`, `docs/a11y/contrast-1440.json` (one entry
per sampled text node, with screen, viewport, font size/weight and ratio). The
booking-reference UUID inside them changes between runs because the E2E booking
differs; nothing else does.

---

## 8. Database, backup and restore

`pnpm verify:neon` — six steps, **PASS 6/6 in 68.6 s** against the configured
database (local PostgreSQL 18.3, host type LOCAL):

| Step | Result |
| --- | --- |
| 1. database target | PASS (host type only; no connection string printed) |
| 2. `prisma migrate deploy` | PASS (1 migration, no pending) |
| 3. constraint + `23P01` probe | PASS |
| 4. integration suite | PASS (44) |
| 5. security suite | PASS (16) |
| 6. concurrency suite | PASS (2) |

The probe (`apps/api/scripts/verify-constraint.ts`) checks the constraint shape
(GiST + `user_id` + half-open `tstzrange` + `&&` + partial on `confirmed`), that an
overlapping insert is rejected with **SQLSTATE 23P01** and leaves no partial row,
that adjacent `[start, end)` bookings are allowed, and that a cancelled booking
frees its slot.

### Backup → restore rehearsal (executed today, `docs/DEPLOYMENT.md` §6–7)

| Step | Result |
| --- | --- |
| `pg_dump --format=custom --no-owner --no-privileges` | exit 0, **33,588 bytes** |
| `CREATE DATABASE slotwise_restore_check` | exit 0 |
| `pg_restore --no-owner --no-privileges --exit-on-error` | exit 0 |
| Row counts, source vs restored | users 4/4, sessions 35/35, event_types 5/5, availability_rules 17/17, bookings 16/16, management_tokens 15/15, outbox_jobs 35/35 — **all OK** |
| Schema objects in the restored copy | `bookings_no_host_overlap / x` present, `btree_gist` + `pgcrypto` present, 1 migration recorded |
| Overlap probe against the restored copy | `RESULT: PASS — exclusion constraint verified` |

The scratch database was dropped afterwards; only `slotwise` remains.

### Account deletion (NFR-04)

`pnpm --filter @slotwise/api delete:account -- --host <email> [--dry-run]` and
`--invitee <email>` run one ordered transaction (bookings → management tokens →
sessions → availability rules → event types → user) and refuse to delete a host
that still has bookings unless `--host` is given. Proven by 7 integration tests;
documented in `docs/PRIVACY.md` (DEV-17).

---

## 9. Performance — NFR-01 (read API p95 < 500 ms)

### Method

`scripts/load.mjs` (`pnpm perf`), with no manual setup:

1. build the API (`tsc -b` + esbuild bundle), seed a dedicated published event
   (`perf-load-test`, all-day availability), start `dist/server.js` on port 4100
   with `NODE_ENV=production`;
2. discard a 5 s warm-up, then measure **20 s per endpoint** with **20 concurrent
   keep-alive connections, closed loop, no think time**;
3. record the wall-clock latency of **every** request and compute p95 exactly
   (nearest-rank); assert p95 ≤ 500 ms with zero errors, zero non-2xx, zero
   timeouts, and a run that finishes within `duration + 60 s`;
4. write `docs/perf/<timestamp>.json`.

`GET /public/:slug` returns a 33.2 KiB payload of 328 slots for the measured
window, so it is the expensive endpoint by construction.

**Why not autocannon for the verdict (DEV-14):** autocannon's HDR histogram has
p50/p75/p90/p97_5/p99 and no p95 key. `--autocannon` is therefore an independent
cross-check at p97_5 (a *stricter* percentile), not the NFR measurement.

### Measurements (7 runs, same code and profile, same machine)

| Run (UTC) | `/public/:slug` p95 | rps | `/slots` p95 | rps | `/slots` p99 / max | Result |
| --- | --- | --- | --- | --- | --- | --- |
| 07:27:31 | 45.2 ms | 692.9 | 230.0 ms | 1.1 | 902,889 / 903,086 ms | **FAIL** — machine stalled (§9.3) |
| 08:08:40 | 54.7 ms | 580.9 | 343.6 ms | 76.6 | 412.3 / 439.9 ms | PASS |
| 08:10:42 | 176.9 ms | 216.8 | **1125.3 ms** | 35.6 | 2017.7 / 2165.2 ms | **FAIL** — host contention (§9.3) |
| 08:13:54 | 77.3 ms | 333.7 | 414.8 ms | 53.6 | 474.7 / 497.9 ms | PASS |
| 08:14:52 | 73.8 ms | 348.7 | 391.8 ms | 55.1 | 410.1 / 424.8 ms | PASS |
| 08:15:48 | 72.2 ms | 359.5 | 384.7 ms | 56.7 | 469.0 / 484.5 ms | PASS |
| **08:36:56 (final)** | **69.3 ms** | 345.2 | **410.6 ms** | 51.7 | 418.8 / 434.0 ms | **PASS** |

Final run, autocannon cross-check (p97_5, not p95): `/public/:slug` 354.8 rps,
p97_5 90 ms, p99 101 ms, max 173 ms, 0 errors; `/public/:slug/slots` 54.0 rps,
p97_5 **626 ms**, p99 1018 ms, max 1051 ms, 0 errors.

### 9.1 Verdict

NFR-01 **passes** on the stated profile: 5 of 6 valid runs, and every run of the
final code state, put `/slots` p95 at 384–415 ms and `/public/:slug` p95 at
69–77 ms, with zero errors and zero non-2xx responses.

Honest caveats, in order of importance:

1. **Headroom is thin.** `/slots` p95 sits at ~80 % of the 500 ms budget. One
   contended run measured 1125 ms. NFR-01 is met, not comfortably met.
2. **The load generator shares the machine with the server.** Both are on one
   8-thread laptop with a browser and an editor resident; the CPU is also running
   the closed-loop client. A dedicated load host would report lower numbers, not
   higher — but this is not a controlled benchmark.
3. **autocannon's p97_5 for `/slots` (626 ms) exceeds 500 ms** in the final run
   while the exact p95 (410.6 ms) does not. p97_5 is the stricter percentile of a
   different sampler with a different connection pattern; the NFR is written as
   p95 and is answered by the harness. Both facts are reported rather than
   picking the flattering one.
4. **Only read endpoints are load-tested.** The booking write path is covered for
   correctness and concurrency, not for latency under load.

### 9.2 What was optimised

The first measurement of `/slots` failed (p95 567 ms). Profiling the generator
showed 7.63 ms per call in `packages/shared/src/slots.ts` — it built a fresh
`Intl.DateTimeFormat` per label. Caching the formatter and using
`formatToParts` brought it to **2.84 ms/call** (2.7×). A byte-for-byte regression
test compares 7,424 labels across 8 zones against the old implementation: 0 diffs.

### 9.3 Two failed runs, kept as evidence

- **07:27:31 — machine stall.** A single `/slots` request took **903 s** inside a
  20 s window; the run spanned 21 minutes instead of ~1.5; 7 connections dropped;
  `pnpm verify:neon` immediately afterwards hung for 30 minutes with no output.
  That is a suspended/stalled host, not latency. p50 (199.6 ms) and p95 (230 ms)
  stayed normal, which is exactly why a hung socket must not be counted as a
  sample. Artifact: `docs/perf/load-2026-10-28T07-27-31-787Z.json`.
- **08:10:42 — host contention.** Same code, same profile, two minutes after a
  passing run: throughput halved (35.6 vs 76.6 rps) and p95 hit 1125 ms. The OS
  reported ~0.5 GB available RAM against a 19.9 GB commit charge. Artifact:
  `docs/perf/load-2026-10-28T08-10-42-113Z.json`.

Both runs exposed a harness weakness that is now fixed (DEV-20): a per-request
timeout (`--request-timeout-ms`, default 30 s), a `timeouts` counter that fails the
run, and a stall guard that fails a run which overshoots `duration + 60 s` with a
message saying the percentiles are not a latency measurement.

---

## 10. CI pipeline (`.github/workflows/ci.yml`)

Seven jobs on `ubuntu-latest`, Node 20, pnpm 12, each installing from the frozen
lockfile:

| Job | Needs | What it runs |
| --- | --- | --- |
| `lint-typecheck` | — | `pnpm lint`, `pnpm typecheck`, `pnpm build` |
| `unit` | lint-typecheck | `pnpm test:unit` (38) |
| `integration` | unit | `postgres:16` service → `prisma migrate deploy` → `verify:constraint` → `pnpm test:integration` (44) |
| `security` | integration | `postgres:16` → migrate → `pnpm test:security` (16) |
| `concurrency` | security | `postgres:16` → migrate → `pnpm test:concurrency` (2) |
| `e2e` | concurrency | `postgres:16` → migrate → Chromium → `pnpm test:e2e` (15); traces uploaded on failure |
| `audit` | — | `pnpm audit --audit-level=high` |

The four database jobs run the **real migrations** and the real suites — no
sqlite, no mocked Prisma. The E2E job drives the real Vite app against the real
API on the same database, so the pipeline reproduces this report's shape on Linux
with PostgreSQL 16.

**Honest limitation:** no GitHub Actions run has been observed. The workflow is
committed and every command it runs has been executed locally (except that CI uses
Node 20 and `postgres:16` while this machine uses Node 22.16 and PostgreSQL 18.3).
The first push will be the pipeline's first real test; a red job must be fixed,
not deleted.

---

## 11. Neon status (DEV-13) — still blocked

`DATABASE_URL` in `.env` and `apps/api/.env` is still the **local** value
(`host type LOCAL`, 54 chars, mtime `2026-10-27T08:45:33Z`). No Neon database has
been migrated, probed or tested. Everything in this report was produced against
local PostgreSQL 18.3, and CI will use `postgres:16`.

This remains a **HARD blocker before M10**: the owner must put the Neon direct
(non-pooled) URL in `.env` and run `pnpm verify:neon` to get 6/6 PASS. The script
runs exactly the six steps in §8 and prints only the host type.

---

## 12. Dependency audit

`pnpm audit --audit-level=high` **failed** on first execution during M6: 3
critical, 3 high. All were fixed rather than muted (DEV-19):

| Advisory | Path | Fix |
| --- | --- | --- |
| tinypool ≤ 2.1.0 — prototype pollution → RCE (2 criticals) | `vitest > tinypool` | Vitest 2.1.9 → **4.1.12** (no tinypool dependency) |
| vite ≤ 6.4.3 — `fs.existsSync` bypass on Windows (high) | `vitest > vite-node > vite` | removed with the Vitest upgrade |
| zod < 4.6.6 — memory exhaustion on oversized constrained collections (high) | `apps/api`, `packages/shared` | zod 3.25.76 → **4.6.7**; all suites re-run green |
| deepmerge-ts < 8.0.0 — stack exhaustion (high) | `prisma > @prisma/config` | `overrides: deepmerge-ts ^8.0.2` in `pnpm-workspace.yaml`; verified by `prisma generate`, `migrate deploy`, `verify:constraint`, `seed:perf` |

Remaining (below the `high` gate, accepted with rationale):

| Severity | Advisory | Why accepted | Action |
| --- | --- | --- | --- |
| moderate | `uuid < 11.1.1` — missing bounds check in v3/v5/v6 with a `buf` | Transitive dev-only dependency; the API never calls uuid with a caller-supplied buffer | Revisit at M10 |
| moderate | `react-router` — open redirect via backslash in `<Link>`/`useNavigate` | SPA-only; navigation targets are internal routes, not user-supplied URLs; no SSR, so the `deserializeErrors()` advisory does not apply | Upgrade to v7 at M7/M10 (major) |

---

## 13. Deviations recorded in M6

| ID | Deviation |
| --- | --- |
| DEV-14 | NFR-01's p95 is computed by the harness (exact per-request sampling); autocannon is a p97_5 cross-check only, because it has no p95. |
| DEV-15 | Production API runs `dist/server.js` (esbuild bundle) because `@slotwise/shared` ships as TypeScript source. |
| DEV-16 | `/health` is liveness only; `/health/ready` is the DB readiness probe (503 when unreachable). |
| DEV-17 | Account/invitee deletion is an operator CLI, not a self-service screen. |
| DEV-18 | Seven per-screen axe tests replaced by 2 viewport scans + contrast + keyboard + reflow; E2E count 19 → 15 while coverage increased. |
| DEV-19 | Vitest 4, zod 4 and a `deepmerge-ts` override to clear `pnpm audit --audit-level=high`. |
| DEV-20 | Load harness hardened with a per-request timeout, a `timeouts` counter and a stall guard after the 07:27 incident. |
| DEV-21 | NFR-01 is reported as a distribution of runs on a contended host, not as a single number; one contention outlier (1125 ms) is published next to the passing runs. |

---

## 14. Known gaps

- **No CI execution observed** (§10). The workflow is unproven on GitHub.
- **Neon unverified** (§11, DEV-13) — hard blocker before M10.
- **Chromium only.** No Firefox/WebKit run; no real mobile device, only emulated
  viewports (390/768/1024/1440 + 640×360).
- **Performance measured on a shared laptop** (§9.1), read endpoints only, and
  `/slots` p95 sits at ~80 % of the NFR budget.
- **Rate limits are raised** for E2E and perf (DEV-11); the real limits are proven
  by the security suite instead.
- **No PITR / off-host restore drill** (`docs/DEPLOYMENT.md` §7); logical dumps
  only.
- **Node version split**: CI runs Node 20, development runs Node 22.16. Worth
  aligning before M10 so the tested runtime is the shipped runtime.
- **Coverage is not measured** (no coverage tool configured); the suites are
  requirement-driven, not percentage-driven.

---

## 15. Reproducing this report

```bash
pnpm install --frozen-lockfile
pnpm --filter @slotwise/api prisma:generate
pnpm db:migrate:deploy            # or prisma:migrate for a dev database

pnpm lint && pnpm typecheck && pnpm build
pnpm test:unit                    # 38
pnpm test:integration             # 44
pnpm test:security                # 16
pnpm test:concurrency             # 2
pnpm test:e2e --retries=0         # 15, boots web + api itself
pnpm audit --audit-level=high
pnpm verify:neon                  # 6 steps: target, migrate, constraint, 3 suites
pnpm perf --autocannon            # NFR-01, writes docs/perf/<stamp>.json
```

All of the above were run in this exact order for this report, on the final code
state, with the exit code of every command checked.
