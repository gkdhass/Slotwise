# Slotwise — Progress

Last updated: 2026-10-28 (M5 swap-in complete; GATE 3 pending).

## Current milestone
M5 "backend swap-in" complete on branch `m5-swapin`. GATE 3 awaits owner review.
M6 is **not** started and will not start without explicit authorisation.

## Milestones
| Milestone | Status | Notes |
|---|---|---|
| Phase 0 — Analysis & setup | Complete | Gate 0 approved (D-01, D-07) |
| M0 Shell | Complete | S01–S11 routes, design tokens, primitives |
| M1 Vertical slice (mock) | Complete | tag `v0.1-mock` |
| M2 Must-haves (persistent) | Complete | Prisma + PostgreSQL, auth, events, availability, public booking transaction, outbox worker, concurrency test |
| M3 Should-haves | Complete | management tokens, cancel/reschedule, booking filters |
| M4 UX fixes | Complete | setup guidance, time-zone clarity, conflict recovery, policy preview |
| M5 Backend swap-in | Complete | All screens on the real API; E2E against real API + DB; security suite; see "Test status" |
| M6 Test & bug-fix | Not started | Blocked until Gate 3 |
| M7 Parity & traceability | Not started | |
| M8 Rebrand sweep | Not started | |
| M9 Launch assets | Not started | |
| M10 Deploy | Not started | |
| Phase 11 (optional) Booking Abuse Detection | Not started | Gated on Gate 3 + owner saying "start Phase 11" |

## Delivered in M5
- Every S01–S11 screen talks to the real API (`apps/web/src/lib/api.ts`). `mockApi` is no longer
  imported by any screen; it survives only as a unit-test fixture inside `App.test.tsx`
  (the module itself is mocked there, not `mockApi`).
- Status handling per DEV-08: `400/401/403/404/409/422/429` each map to a specific user message;
  form values are preserved on `409`; success is never rendered before the server confirms.
- Policy preview before booking (S05 `data-testid="policy-preview"`, S06 `data-testid="policy-public"`).
- Time zone shown beside every time and in confirmation (S09 shows invitee **and** host zone, S10 too).
- Conflict recovery returns to slot selection with the invitee input intact (S07 keeps
  `location.state`, `data`-derived date now uses the **event** zone, not the browser zone).
- Security: `helmet` (incl. `Referrer-Policy: no-referrer`), CORS exact allow-list, rate limits on
  login/register/slots/booking, CSRF on all state-changing routes (DEV-07), `no-store` +
  `no-referrer` on the manage route, and a production startup guard that refuses to boot when
  `CSRF_DISABLED=true` or `SESSION_SECRET`/`DATABASE_URL` is missing.

## Fixes (each with an acceptance criterion and a test)
| Fix | Acceptance criterion | Test |
|---|---|---|
| Policy preview before booking | S05 and S06 render the cancellation policy before the invitee commits | `tests/e2e/core-loop.spec.ts` (S02→S05), `public.spec.ts` (S06), `App.test.tsx` (policy-public) |
| Time zone beside every time | The confirmation shows the invitee's zone **and** the host's zone; S10 keeps doing so | `core-loop.spec.ts` "S06 → S09 → S10" |
| Conflict recovery | A `409` sends the invitee back to slot selection with name/email/note intact and no false success | `core-loop.spec.ts` "a taken slot returns to slot selection…" |
| S07 date derivation | The date input is derived in the zone the slots are filtered by (wait for `tzResolved`) | same conflict test (previously failed when browser TZ ≠ event TZ) |
| S10 reschedule date | The reschedule date defaults to the booking's own date in `displayTimezone` | `core-loop.spec.ts` "S10 reschedule…" |

## Test status (all executed 2026-10-28, real commands, no skips)
| Command | Result |
|---|---|
| `pnpm lint` | 0 errors, 0 warnings (all 3 packages) |
| `pnpm typecheck` | clean (all 3 packages) |
| `pnpm test` | 14 passed — shared 7, api 2, web 5 |
| `pnpm --filter @slotwise/api test:integration` | 32 passed (4 files) |
| `pnpm --filter @slotwise/api test:security` | 16 passed |
| `pnpm --filter @slotwise/api test:concurrency` | 2 passed |
| `pnpm test:e2e` (headless) | 19 passed |
| `pnpm build` | api + web built |

### Required test IDs (Gate 3)
All present and passing in `apps/api/tests/integration/flows.test.ts`:
F00-H1, F00-E1, F00-N1, F01-H1, F01-E1, F01-N1, F02-H1, F02-E1, F02-N1, F02-H2,
F03-H1, F03-E1, F03-N1, F03-H2.

Additional required coverage:
- Outbox rollback leaves no job; retry with exponential backoff; bounded failure — `outbox.test.ts`.
- Invalid/expired management token reveals nothing — `flows.test.ts` (denial bodies compared field by field).
- Canceled booking frees the slot — `flows.test.ts`.
- API-level time zones: DST spring-forward/fall-back and host≠invitee zones — `timezone.test.ts`.
- Rate limits → 429, helmet, CORS allow-list, manage route headers, production guard — `security.test.ts`.
- CSRF enforced (bypass genuinely off) — `security.test.ts` with `vitest.security.config.ts`.

## Deviations / risks
- **DEV-13 (HARD BLOCKER before M10): Neon verification is deferred.** All results in this document
  were produced on **local PostgreSQL 18.3**. The Neon databases have not been exercised: no
  migration, no `23P01` probe, no suites. The owner must run `pnpm verify:neon` with the Neon
  direct URL in `.env` and get 6/6 PASS before any deploy work starts.
- **DEV-05 stands: the dev database is local PostgreSQL 18.3, not Neon.** `.env` and
  `apps/api/.env` still point at `postgresql://slotwise:slotwise@localhost:5432/slotwise`, so all
  DB-backed results above were produced against local PG 18, not the Neon instance the Gate 2
  instruction asked for. The owner must paste the Neon **direct** (non-pooled) URL into `.env`
  before Neon-specific results can be reported. Migration SQL is provider-agnostic.
- DEV-10/DEV-11: Playwright boots two web servers rather than `pnpm dev`, and the E2E servers run
  with raised rate limits (real limits proven by `tests/security`).
- `test:e2e` binds Vite to `127.0.0.1`; `http://127.0.0.1:5173` and `http://localhost:5173` both work.
- No CI run has been performed for M5 (no CI pipeline available locally).

## Open questions for owner (Gate 3)
1. Approve M5 and authorise M6?
2. Provide the Neon direct `DATABASE_URL` so the DB suites can be re-run against Neon.
3. Confirm the E2E approach (two servers + raised limits) is acceptable.
