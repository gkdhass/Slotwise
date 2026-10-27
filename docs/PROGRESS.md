# Slotwise — Progress

Last updated: 2026-10-27 (Phase 0).

## Current milestone
Phase 0 — Analysis & setup. Status: in progress (Gate 0 pending owner confirmation of D-01 and D-07).

## Milestones
| Milestone | Status | Notes |
|---|---|---|
| Phase 0 — Analysis & setup | In progress | Docs written; repo scaffolded; Gate 0 pending |
| M0 Shell | Not started | Blocked on Gate 0 |
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