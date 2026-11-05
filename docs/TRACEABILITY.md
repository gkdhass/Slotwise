# TRACEABILITY.md — feature → screen → flow → table → route → milestone → test

Every row of the Implementation Plan's traceability matrix
(`docs/source/06_Implementation_Plan_Professionally_Formatted.pdf` §12) is
reproduced below with **real paths, real route mounts and real test names** as
they exist in this repository. Rows that were planned but not delivered say so.

- API mounts: `apps/api/src/index.ts` (`/api/v1/auth`, `/api/v1/event-types`,
  `/api/v1/public`, `/api/v1/bookings`, `/api/v1/manage`, `/api/v1/worker`).
- Screens and routes: `apps/web/src/App.tsx` → `apps/web/src/screens/S*.tsx`.
- Tables: `apps/api/prisma/schema.prisma` (+ `apps/api/prisma/migrations/`).
- Test IDs: `apps/api/tests/integration/flows.test.ts` (F00–F03), other suites as
  cited. Full test inventory: `docs/TEST_REPORT.md` §4–§7.

## 1. Implementation Plan matrix (§12), row by row

| # | Feature | Screen | Flow | Table(s) | API route (as mounted) | Planned | Delivered | Test (ID → real name, file) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Account registration | S01 `S01Auth.tsx` | F00 | `users`, `sessions` | `POST /api/v1/auth/register`, `POST /api/v1/auth/verify-email` | M2 | M2 | `F00-H1` "register -> verify -> login -> create -> availability -> publish" (`flows.test.ts`); `auth.test.ts` "register → verify → login → logout" |
| 2 | Authentication guard | S01 `S01Auth.tsx` | F00 | `users`, `sessions` | `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me` | M2/M5 | M2/M5 | `F00-N1` "an unverified owner cannot publish" (`flows.test.ts`); `security.test.ts` "register, login and logout succeed end-to-end once the token is echoed"; `auth.test.ts` session-revocation cases |
| 3 | Event listing | S02 `S02Dashboard.tsx` | F01 | `event_types` | `GET /api/v1/event-types` | M2 | M2 | `F01-H1` "creating and publishing makes the event publicly bookable" (`flows.test.ts`) |
| 4 | Event CRUD | S03 `S03EventEditor.tsx` | F01 | `event_types` | `POST /api/v1/event-types`, `PATCH /api/v1/event-types/:id`, `DELETE /api/v1/event-types/:id` (= archive) | M2 | M2 | `F01-H1` (`flows.test.ts`); `F01-H2` "archiving an event hides it from the public page and the slots API"; `F01-N1` "another owner cannot read, edit or delete the event" |
| 5 | Availability | S04 `S04Availability.tsx` | F01 | `availability_rules` | `GET/PUT /api/v1/event-types/:id/availability` | M2 | M2 | `F01-E1` "invalid duration and invalid availability ranges are rejected" (`flows.test.ts`) |
| 6 | Publish | S05 `S05PreviewPublish.tsx` | F00/F01 | `event_types` | `PATCH /api/v1/event-types/:id` (`isPublished`) | M2 | M2 | `F00-H1` "… → publish" and `F00-N1` "an unverified owner cannot publish" (`flows.test.ts`) |
| 7 | Public event page | S06 `S06PublicEvent.tsx` | F02 | `event_types` | `GET /api/v1/public/:slug` | M2 | M2 | `F02-H1` (`flows.test.ts`); `public.spec.ts` "S06 shows the published event, its duration, host zone and policy" and "S06 shows a generic unavailable page for an unknown slug" |
| 8 | Slot selection | S07 `S07SlotSelector.tsx` | F02 | `availability_rules`, `bookings` | `GET /api/v1/public/:slug/slots` | M2/M5 | M2/M5 | `F02-E1` "a slot taken by someone else returns 409 SLOT_UNAVAILABLE"; `F02-H3` "a booking that starts before the window still blocks slots inside it"; `F01-E2` (31-day cap); `timezone.test.ts` DST spring-forward/fall-back; `public.spec.ts` "S07 lists real slots in the host time zone…", "S07 drops the previous day's slots and selection when the date changes" |
| 9 | Invitee details | S08 `S08InviteeDetails.tsx` | F02 | `bookings` | `POST /api/v1/public/:slug/bookings` | M2 | M2 | `F02-N1` "malformed, unpublished and invalid-slot bookings are rejected" (`flows.test.ts`) |
| 10 | Atomic booking | S08/S09 `S08InviteeDetails.tsx`, `S09Confirmation.tsx` | F02 | `bookings` (+ `bookings_no_host_overlap`) | `POST /api/v1/public/:slug/bookings` | M5 | M2 | `F02-H1` "one booking creates a confirmed booking, a management token and an outbox job"; `booking.test.ts` "50 parallel requests for the same slot -> exactly one confirmed booking" and "overlapping slots across two event types -> at most one confirmed booking" |
| 11 | Idempotent booking | S08/S09 | F02 | `bookings` (`UNIQUE(user_id, idempotency_key)`) | `POST /api/v1/public/:slug/bookings` | M5 | M2 | `F02-H2` "retrying with the same idempotency key replays the same outcome" (`flows.test.ts`) |
| 12 | Confirmation email | S09 `S09Confirmation.tsx` | F02 | `outbox_jobs`, `bookings` | `POST /api/v1/public/:slug/bookings` → `POST /api/v1/worker/run-outbox` | M5 | M2/M5 | `F02-H1` (outbox row asserted); `outbox.test.ts` "rollback leaves no outbox job…", "sends a pending job, marks it sent, and does not resend it", "retries with exponential backoff, then stops after the bounded attempt limit", "does not claim jobs that are not yet due", "the worker HTTP endpoint is protected by the shared secret" |
| 13 | Cancellation | S10 `S10Management.tsx` | F03 | `bookings`, `management_tokens` | `POST /api/v1/manage/:token/cancel` | M3/M5 | M3 | `F03-H1` "canceling releases the slot for a new booking"; `F03-N1` "invalid and expired tokens reveal nothing" (`flows.test.ts`) |
| 14 | Rescheduling | S10/S07 | F03 | `bookings`, `management_tokens` | `POST /api/v1/manage/:token/reschedule` | M3/M5 | M3 | `F03-E1` "a reschedule into an occupied slot keeps the original booking unchanged"; `F03-H2` "a successful reschedule moves the booking and frees the old slot"; `core-loop.spec.ts` "S10 reschedule moves the booking and frees the previous slot" |
| 15 | Booking list | S11 `S11BookingList.tsx` | F03 | `bookings` | `GET /api/v1/bookings` (`?status&from&to`) | M2 | M2 | `F03-H3` "the owner booking list filters by status and date and never leaks another host"; `auth.test.ts` "owner B cannot list owner A's bookings (scoped)"; `core-loop.spec.ts` (S11 renders heading + status filter) |
| 16 | Independent rebrand | S01–S11 | All | N/A | All UI routes | M8 | **Not started** | M8 rebrand sweep — **open** (gap G-01) |

Row 16 is the only matrix row that is not delivered: M8 has not been authorised.
It is carried in `docs/GAPS.md` as G-01.

## 2. Requirement → evidence (FR and NFR)

The matrix above is screen-shaped. The requirement register in
`docs/00_ANALYSIS.md` §1 is covered as follows; scores are in `docs/PARITY.md`.

| Req | Priority | Where it lives | Primary evidence |
| --- | --- | --- | --- |
| FR-01 register/verify/login/logout | must | `apps/api/src/routes/auth.ts`, `services/authService.ts`, `apps/web/src/screens/S01Auth.tsx` | `F00-H1`, `F00-N1`, `auth.test.ts` (7), `security.test.ts` (CSRF on auth) |
| FR-02 event create/edit/archive | must | `routes/eventTypes.ts`, `S02`–`S03` | `F01-H1`, `F01-H2` (archive), `F01-N1`, `F01-E1` |
| FR-03 weekly availability + zone | must | `routes/eventTypes.ts` (`PUT /:id/availability`), `S04Availability.tsx`, `packages/shared/src/slots.ts` | `F01-E1`, `timezone.test.ts` (7), `slots.test.ts` (9) |
| FR-04 visitor sees published event + slots | must | `routes/public.ts`, `S06`, `S07` | `F02-H1`, `F01-H2` (archived → 404), `F01-E2`, `public.spec.ts` |
| FR-05 booking without account | must | `routes/public.ts` (`POST /:slug/bookings`), `S08`, `S09` | `F02-H1`, `F02-N1`, `core-loop.spec.ts` end-to-end booking |
| FR-06 no overlapping confirmed bookings per host | must | `bookings_no_host_overlap` EXCLUDE (GiST), booking transaction | `booking.test.ts` (2 concurrency tests), `F02-E1`, `F03-E1`, `verify:constraint` probe |
| FR-07 confirmation email queued | must | `outbox_jobs`, `worker/emailWorker.ts`, `POST /api/v1/worker/run-outbox` | `F02-H1`, `outbox.test.ts` (5) |
| FR-08 cancel/reschedule via secure token | should | `routes/manage.ts`, `S10Management.tsx` | `F03-H1`, `F03-H2`, `F03-E1`, `F03-N1`, `core-loop.spec.ts` |
| FR-09 clear setup/conflict messages | should | `S03`–`S08` error surfaces, `fieldErrors` envelope | `F00-E1`, `F01-E1`, `F02-N1`, `core-loop.spec.ts` "a taken slot returns to slot selection with the invitee input preserved" |
| FR-10 paid bookings | could | — (D-08) | Not built, by decision. Gap G-02. |
| NFR-01 read API p95 < 500 ms | must | `packages/shared/src/slots.ts`, `routes/public.ts`, `scripts/load.mjs` | `docs/TEST_REPORT.md` §9.4: `/slots` p95 184.6 / 212.0 / 210.7 ms (3 runs); `/public/:slug` 59.5 / 61.7 / 65.9 ms |
| NFR-02 WCAG 2.2 AA, keyboard loop, axe clean | must | `apps/web/src/components/*`, `tests/e2e/a11y.spec.ts` | `a11y.spec.ts` "axe and contrast: every screen at 390/1440 px", "keyboard-only core loop…", "reflow: no horizontal overflow…"; contrast audit `docs/a11y/contrast-*.json` |
| NFR-03 zero double bookings | must | EXCLUDE constraint + transaction ordering | `booking.test.ts` (50 parallel requests → 1 confirmed; cross-event overlap → ≤ 1) |
| NFR-04 minimal invitee data, retention, deletion | must | `services/accountDeletion.ts`, `docs/PRIVACY.md` | `accountDeletion.test.ts` (7); `docs/PRIVACY.md` inventory/retention |
| NFR-05 logs, request IDs, health, error hook | must | `lib/logger.ts`, `middleware/requestId.ts`, `lib/errorMonitor.ts`, `/health`, `/health/ready` | `observability.test.ts` (4), `logger.test.ts` (5), `requestId.test.ts` (5), `errorMonitor.test.ts` (7), `health.test.ts` (2) |
| NFR-06 verified at 390/1440 (also 768/1024) | must | Tailwind breakpoints, `Shell` | `a11y.spec.ts` viewport scans (390/768/1024/1440) + reflow test |

## 3. Screens → routes (for the report's design chapter)

| Screen | File | Route | Access |
| --- | --- | --- | --- |
| S01 | `apps/web/src/screens/S01Auth.tsx` | `/login`, `/register` | public |
| S02 | `S02Dashboard.tsx` | `/app` | owner (RequireAuth) |
| S03 | `S03EventEditor.tsx` | `/app/events/new`, `/app/events/:id/edit` | owner |
| S04 | `S04Availability.tsx` | `/app/events/:id/availability` | owner |
| S05 | `S05PreviewPublish.tsx` | `/app/events/:id/preview` | owner |
| S06 | `S06PublicEvent.tsx` | `/book/:slug` | public |
| S07 | `S07SlotSelector.tsx` | `/book/:slug/slots` | public |
| S08 | `S08InviteeDetails.tsx` | `/book/:slug/details` | public |
| S09 | `S09Confirmation.tsx` | `/booking/confirmed/:reference` | public |
| S10 | `S10Management.tsx` | `/manage/:token` | token (bearer URL) |
| S11 | `S11BookingList.tsx` | `/app/bookings` | owner |
| S12 | — | `/app/admin/flags` | Phase 11 only, not built (A-07) |

## 4. How to re-verify this document

```bash
pnpm test:integration     # 48 tests: F00/F01/F02/F03 IDs + auth/timezone/outbox/observability/deletion
pnpm test:security        # 16
pnpm test:concurrency     # 2
pnpm test:e2e             # 16 (core-loop, public, a11y)
# the ID list itself, on Windows PowerShell:
Select-String -Path apps/api/tests/integration/flows.test.ts -Pattern 'it\("F0'
```
