# Slotwise — Progress

Last updated: 2026-10-27 (Phase 0).

## Current milestone
M1 Vertical slice (mock) — complete on branch `m1-slice`. GATE 1 pending (demo walkthrough).

## Milestones
| Milestone | Status | Notes |
|---|---|---|
| Phase 0 — Analysis & setup | Complete | Gate 0 approved (D-01 PostgreSQL, D-07 Render/Railway) |
| M0 Shell | Complete | Routes S01–S11, tokens, primitives, mock data, real lint/typecheck/tests |
| M1 Vertical slice (mock) | Complete | Core loop S02-S10 with mock layer; lint/typecheck/tests pass; build passes |
| M1 Vertical slice (mock) | Not started | |
| M2 Must-haves (persistent) | Not started | |
| M3 Should-haves | Not started | |
| M4 UX fixes | Not started | |
| M5 Backend swap-in | Not started | |
| M6 Test & bug-fix | Not started | |
| M7 Parity & traceability | Not started | |
| M8 Rebrand sweep | Not started | |
| M9 Launch assets | Not started | |
| M10 Deploy | Not started | |
| Phase 11 (optional) Booking Abuse Detection | Not started | Gated on Gate 3 + owner approval |

## Task IDs
- Phase 0: scaffold, docs, CI, docker, env — in progress.

## Test status
None yet (no code). Test matrix defined in master prompt §11.

## Open risks
- D-01 and D-07 pending owner confirmation.
- Docker not available locally; dev Postgres may need native install or remote (Neon).
- No pnpm lockfile yet (scaffold only).

## Open questions for owner (Gate 0)
1. Confirm D-01: PostgreSQL.
2. Confirm D-07: Vercel serverless + cron worker route, or Render/Railway.
3. Approve proceeding to M0 after Gate 0.