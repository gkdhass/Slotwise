# Slotwise — Decisions Log

Format: ID | Decision | Reason / source | Date | Status.

## A. Decisions already made (master prompt §2)

| ID | Decision | Reason | Date | Status |
|---|---|---|---|---|
| D-01 | Database = PostgreSQL (Neon/Supabase for hosting; local dev via Neon dev branch or native PG16). Do NOT use MongoDB. | No-double-booking guarantee needs GiST exclusion constraint; MongoDB cannot provide it. Confirmed at Gate 0: PostgreSQL only; no MongoDB/SQLite/in-memory substitutes for integration or concurrency tests. | 2026-10-27 | **Confirmed at Gate 0** |
| D-02 | ORM = Prisma for CRUD/migrations + raw SQL migrations for extensions and the exclusion constraint; booking transaction may use `$queryRaw`/`$transaction`. | Prisma cannot express EXCLUDE constraints natively. | 2026-10-27 | Accepted |
| D-03 | Language = TypeScript on frontend and backend. | Maintainability; shared types. | 2026-10-27 | Accepted |
| D-04 | Frontend = React + Vite + Tailwind CSS. Backend = Node.js + Express (modular monolith). Validation = Zod. | PRD/TRD. | 2026-10-27 | Accepted |
| D-05 | Auth = server-side sessions, HTTP-only cookie, session token stored hashed, Argon2id passwords, CSRF protection. | TRD §7. | 2026-10-27 | Accepted |
| D-06 | Email = Resend (or Nodemailer + Ethereal/Mailpit in dev). Emails only sent by outbox worker after commit. | TRD §2, PRD FR-07. | 2026-10-27 | Accepted |
| D-07 | Hosting = Vercel for frontend only. API + outbox worker on a long-running Node host (Render or Railway), NOT Vercel serverless. Reason: SKIP LOCKED polling, stable DB connections, and Prisma connection handling. Worker must be runnable as (a) a separate process and (b) a secret-protected HTTP route, so the hosting choice stays reversible. | Decided at Gate 0 (2026-10-27). Vercel serverless rejected for the API due to connection/worker constraints. | 2026-10-27 | **Decided at Gate 0** |
| D-08 | Payments, Google/Microsoft calendar, reminders = out of scope (feature-flagged off, not built). | PRD "could/defer". | 2026-10-27 | Accepted |
| D-09 | Currency symbol in PRD pricing table unreadable (rendered ■); assume ₹ (INR). Pricing is a hypothesis shown only in docs, not implemented. | Ambiguity. | 2026-10-27 | Accepted |
| D-10 | IEEE paper is NOT about scheduling. Incorporated only as optional, advisory "Booking Abuse Detection" research module (Phase 11), built after core is shippable. | Paper domain (threat detection via deep transfer learning) does not match Slotwise docs. | 2026-10-27 | Accepted (optional, gated) |

## B. Conflicts found during analysis (see 00_ANALYSIS §6)

| ID | Conflict | Resolution |
|---|---|---|
| C-01 | DB "unresolved": MongoDB preference vs required PostgreSQL DDL | Resolved by D-01 (PostgreSQL) |
| C-02 | ORM choice depends on DB | Resolved by D-02 (Prisma) |
| C-03 | Vercel serverless vs persistent worker | Resolved by D-07 (verify limits; fallback Render/Railway) |
| C-04 | Pricing currency unreadable | Resolved by D-09 (₹ INR, hypothesis) |
| C-05 | IEEE paper domain mismatch | Resolved by D-10 (optional Phase 11) |
| C-06 | Paper proposes automated threat response; PRD excludes zero-touch automated security response | Phase 11 is advisory-only; rate limiting stays real defence |
| C-07 | TRD mentions Stripe webhook; PRD defers paid bookings | D-08: payments out of scope |
| C-08 | TRD "webhooks optional" vs master prompt "no webhook/signature code needed" | Stripe webhook route deferred/optional; no payments in MVP |
| C-09 | Paper internally inconsistent (image datasets vs network traffic text; numbers) | Do not reuse paper's numbers; report own measured values |
| C-10 | updated_at maintenance left to app or trigger | Use DB trigger in migrations |

## B2. Deviations recorded during execution

| ID | Deviation | Reason |
|---|---|---|
| DEV-01 | Atomic booking transaction + exclusion constraint + idempotency moved from M5 to M2 (originally M5 per master prompt §10). | Gate 1 approval (2026-10-27): implement `bookings_no_host_overlap` and full booking transaction now, with concurrency tests in `tests/concurrency`. |
| DEV-02 | Slot-generation and time-zone logic moved from `apps/web` mock into `packages/shared` as pure, unit-tested functions. | Gate 1 approval: both API and web import from shared; mockApi retained only for unit tests. |
| DEV-03 | Playwright + axe added in M2 (originally M6). | Gate 1 approval: smoke test of core loop + axe on S06–S09 now. |
| DEV-04 | Web screens still consume mockApi (localStorage) in M2; real API client implemented in `apps/web/src/lib/api.ts` but screen wiring deferred. | Backend + tests prioritized; mechanical swap (same signatures) deferred to M3/M4. mockApi retained for unit tests. |
| DEV-05 | Dev database is local PostgreSQL 18 (not Neon) because `.env` was not populated; CI uses PostgreSQL 16 service container. | User can switch to Neon by updating `DATABASE_URL`; migration SQL is provider-agnostic. |
| DEV-06 | **Supersedes DEV-04.** All S01–S11 screens now call the real API client (`apps/web/src/lib/api.ts`); `mockApi` is no longer imported by any screen and survives only as a unit-test fixture. | M5 scope: "wire every screen to the real API". Verified by `apps/web/src/App.test.tsx` (mock of `./lib/api`, not `mockApi`). |
| DEV-07 | CSRF protection applied to *all* state-changing auth routes (`register`, `verify-email`, `login`, `logout`, `password-reset/*`), plus a `GET /api/v1/auth/csrf` bootstrap endpoint the SPA calls before its first mutation. The public booking route deliberately keeps **no** CSRF (it carries no ambient authority). | Closes the login-CSRF gap found while writing the enforced-CSRF test suite. |
| DEV-08 | Validation status split: schema/format failures → `400 VALIDATION_ERROR`; business-rule failures (unknown time zone, slot not on the availability grid, inverted/over-long window, overlapping availability) → `422 UNPROCESSABLE`. | Zod cannot express calendar/business rules; keeping the codes distinct lets the UI show "fix your input" vs "that time is no longer valid". |
| DEV-09 | Idempotent booking replay returns `200` with the original reference, `managementToken: null` and `replayed: true`. | A replay must not hand out a second copy of a bearer-style token; the first token was already delivered by email. |
| DEV-10 | Playwright starts two web servers (`web`, `api`) instead of `pnpm dev`, and Vite is pinned to `host: "127.0.0.1"`. | `pnpm --parallel`'s output multiplexer stalls when its stdout is a pipe (Playwright's spawn), so the stack never became ready; and Vite's default resolves `localhost` to `::1` on Windows, which the `127.0.0.1` readiness probe cannot reach. Debugged with `DEBUG=pw:webserver`. |
| DEV-11 | E2E servers run with raised rate limits (`RATE_LIMIT_*`) via `webServer.env`. The real limits are still enforced and proven by `tests/security`. | 19 browser tests legitimately exceed a 10-per-15-min login bucket; the production limits remain untested-by-E2E but fully covered by the security suite. |
| DEV-12 | `tests/e2e/.auth/owner.json` (Playwright storage state) is git-ignored. | It contains a live session cookie; committing it would leak a credential. |

## C. Assumptions recorded (master prompt rule 6)

- A-01: Target persona = independent tutor (provisional guess; no verified user pain).
- A-02: Pain points (setup friction, time-zone uncertainty, conflict recovery) are hypotheses until usability testing.
- A-03: KPI targets are initial targets, not measured.
- A-04: Brand name "Slotwise" provisional; trademark/domain/handle checks are owner's.
- A-05: Logo = original geometric calendar-grid/open-slot mark; to be created in M0/M8.
- A-06: Host/invitee example zones = Asia/Kolkata vs America/New_York for DST tests.
- A-07: Phase 11 ML module starts only after Gate 3 passes AND owner says "start Phase 11".
- A-08: pnpm (not npm) for workspaces; pnpm 12.15.0 installed locally. Docker not available locally → Postgres via native install or remote (Neon) for dev; docker-compose.yml still provided for environments with Docker.
- A-09: Node.js v22.16.0; git 2.53.0.