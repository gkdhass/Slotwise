# Slotwise — Phase 0 Analysis

> Generated at the start of Phase 0. Source documents: `/docs/source/01_PRD … 06_Implementation_Plan` + `IEEE Paper.pdf`. Decision priority per master prompt §2.

## 1. Requirement inventory

### Functional (PRD §5)
| ID | Requirement | Priority | Milestone | Acceptance criterion |
|---|---|---|---|---|
| FR-01 | Owner registers, verifies email, logs in/out | must | M2/M5 | Unverified cannot publish; session revoked on logout |
| FR-02 | Create/edit/archive event type | must | M2 | Visible only to owner until published |
| FR-03 | Weekly availability + time zone | must | M2 | Invalid/overlapping local ranges rejected |
| FR-04 | Visitor views published event and slots | must | M2 | Unpublished/archived not exposed |
| FR-05 | Visitor books without account | must | M2/M5 | Valid request creates exactly one booking |
| FR-06 | No overlapping confirmed bookings per host (across event types) | must | M5 | Concurrent test yields at most one |
| FR-07 | Booking confirmation + email queued | must | M5 | Outbox row exists only if transaction committed |
| FR-08 | Cancel/reschedule via secure token | should | M3 | Invalid/expired token discloses nothing |
| FR-09 | Clear, actionable setup and conflict messages | should | M4 | Recover from conflict without losing input |
| FR-10 | Paid bookings | could | — | Disabled / not built |

### Non-functional (PRD §6)
NFR-01 read API p95 < 500 ms · NFR-02 WCAG 2.2 AA, keyboard core loop, axe clean · NFR-03 zero double bookings · NFR-04 minimal invitee data, retention, deletion path · NFR-05 structured logs, request IDs, `/health`, error monitoring hook · NFR-06 verified at 390 px and 1440 px (also 768/1024).

### Business rules (PRD §9, DB §4)
- Only published, non-archived events publicly bookable.
- Booking `start < end`; duration equals event duration.
- All instants in UTC (`TIMESTAMPTZ`); IANA zone names stored separately; display zone always shown.
- Confirmed booking may not overlap another confirmed booking for same host.
- Email queued in same transaction, sent after commit; retries idempotent and bounded with exponential backoff.
- API requires idempotency key on booking creation (PG `UNIQUE(user_id, idempotency_key)` does not dedupe NULLs).

## 2. Screen inventory (Application Flow §2)
| ID | Screen | Route | Access | States |
|---|---|---|---|---|
| S01 | Sign in / register | `/login`, `/register` | public | empty, loading, invalid, success, mobile |
| S02 | Dashboard | `/app` | owner | empty, loading, filled, error |
| S03 | Event editor | `/app/events/new`, `/app/events/:id/edit` | owner | empty, dirty, saving, error |
| S04 | Availability editor | `/app/events/:id/availability` | owner | empty, invalid, saving, filled |
| S05 | Preview / publish | `/app/events/:id/preview` | owner | draft, published, saving, error |
| S06 | Public event page | `/book/:slug` | public | loading, not found, unpublished, filled |
| S07 | Slot selector | `/book/:slug/slots` | public | loading, no slots, selected, stale |
| S08 | Invitee details | `/book/:slug/details` | public | empty, invalid, submitting, expired slot |
| S09 | Confirmation | `/booking/confirmed/:reference` | public | loading, success, not found |
| S10 | Booking management | `/manage/:token` | token | valid, expired, canceled, error |
| S11 | Owner booking list | `/app/bookings` | owner | empty, loading, filled, error |
| S12 | (Phase 11 only) Flagged activity | `/app/admin/flags` | admin/owner | advisory only |

## 3. Flow inventory (Application Flow §3–6)
- **F00** Registration & first setup: S01→S02→S03→S04→S05. H1 register+verify+publish; E1 missing fields → inline validation; N1 unverified cannot publish. Target ≤ 8 meaningful clicks.
- **F01** Event management: S02→S03→S04→S05. H1 create+publish; H2 edit published reflects publicly; E1 invalid duration/range rejected; N1 cross-owner edit forbidden (403, no mutation). Target ≤ 5 clicks.
- **F02** Public booking: S06→S07→S08→S09. H1 one booking + confirmation; H2 idempotent retry same outcome; E1 slot taken → 409 + refresh path, form preserved; N1 invalid email/unpublished/expired slot/malformed rejected. Target ≤ 5 clicks.
- **F03** Management: cancel S09→S10 (≤ 3 clicks); reschedule S09→S10→S07→S09 (≤ 4 clicks). H1 cancel releases slot; H2 reschedule reserves new before releasing old; E1 occupied destination keeps old; N1 invalid/expired token → generic denial.

## 4. API contract inventory (TRD §5, master prompt §6)
Base `/api/v1`. Error envelope `{ error: { code, message, requestId, fieldErrors } }`.
- Auth: `POST /auth/register`, `/auth/login`, `/auth/logout`; `GET /me`; email verify + password reset (single-use, hashed, expiring).
- Events: `GET/POST /event-types`; `PATCH/DELETE /event-types/:id` (DELETE = archive); `PUT /event-types/:id/availability`.
- Public: `GET /public/:slug`; `GET /public/:slug/slots?from&to&tz`; `POST /public/:slug/bookings`.
- Owner: `GET /bookings` (filters by date/status).
- Management: `POST /manage/:token/cancel`, `/manage/:token/reschedule`.
- Ops: `GET /health`; (optional) `POST /webhooks/stripe` (payments deferred); (optional) secured worker route for outbox.

## 5. Database inventory (Backend Schema §3)
Seven tables, UUID PKs, `TIMESTAMPTZ`, `created_at/updated_at` on all (updated_at via trigger). Extensions `pgcrypto`, `btree_gist`.
- `users` (email UNIQUE, password_hash, role CHECK owner|admin, email_verified_at, deleted_at, timestamps)
- `sessions` (user_id→users CASCADE, token_hash UNIQUE, expires_at, revoked_at; idx user_id, expires_at)
- `event_types` (user_id→users CASCADE, title 1–120, slug UNIQUE, description, duration_minutes 5–480, location_type custom|phone|online, location_details, timezone, is_published default false, archived_at; idx user_id, (user_id,is_published,archived_at))
- `availability_rules` (event_type_id→event_types CASCADE, weekday 0–6, start_local TIME, end_local TIME, timezone, CHECK start_local<end_local; idx event_type_id, (event_type_id,weekday))
- `bookings` (user_id→users RESTRICT, event_type_id→event_types RESTRICT, invitee_name 1–120, invitee_email, invitee_note, start_at, end_at, timezone, status CHECK confirmed|canceled|completed|no_show default confirmed, idempotency_key, CHECK start_at<end_at, UNIQUE(user_id,idempotency_key); idx user_id, event_type_id, start_at, status, (user_id,start_at DESC))
- `bookings_no_host_overlap`: `EXCLUDE USING gist (user_id WITH =, tstzrange(start_at, end_at, '[)') WITH &&) WHERE (status = 'confirmed')`
- `management_tokens` (booking_id→bookings CASCADE, token_hash UNIQUE, expires_at, used_at; idx booking_id, expires_at)
- `outbox_jobs` (booking_id→bookings SET NULL, job_type CHECK booking_confirmation|booking_canceled|booking_rescheduled, status CHECK pending|processing|sent|failed default pending, payload JSONB, attempts ≥0, available_at, processed_at, last_error_code; idx (status,available_at), booking_id)

## 6. Cross-document inconsistencies found
| # | Conflict | Resolution (recorded in DECISIONS.md) |
|---|---|---|
| C-01 | DB "unresolved": PRD/TRD prefer MongoDB; schema requires PostgreSQL DDL + exclusion constraint | D-01: PostgreSQL (confirm at Gate 0) |
| C-02 | ORM depends on DB choice (Prisma vs Mongoose) | D-02: Prisma + raw SQL migrations |
| C-03 | Hosting: Vercel serverless vs persistent worker for outbox | D-07: prefer Vercel serverless + cron worker route; verify limits; else Render/Railway |
| C-04 | Pricing currency rendered as ■ (unreadable) in PRD §11 | D-09: assume ₹ (INR); hypothesis only; not implemented |
| C-05 | IEEE paper domain (deep transfer learning threat detection on image datasets) does not match scheduling domain | D-10: optional advisory "Booking Abuse Detection" module only, Phase 11, never auto-block |
| C-06 | PRD mentions "production zero-touch security response system" as non-goal; paper §III.G proposes automated threat response | D-10: advisory-only, rate limiting stays real defence |
| C-07 | TRD mentions payments/Stripe webhook; PRD defers paid bookings (could) | D-08: payments out of scope, feature-flagged off, not built |
| C-08 | TRD says webhooks optional; master prompt says webhook/signature code not needed | Keep Stripe webhook route optional/deferred; no payments in MVP |
| C-09 | TRD says "MobileNetV2 / Exception" and lists image datasets but text describes network traffic — internally inconsistent paper | D-10 note: do not reuse paper's numbers; report own measured values |
| C-10 | Updated_at maintenance left to app or trigger | Use DB trigger in migrations (DB §4 note) |

## 7. Assumptions (stated, not facts)
- Target persona independent tutor is a provisional guess (PRD §3); no user pain verified.
- All positioning options A/B/C have 0 review sources; pain points are hypotheses.
- Pricing (₹299/₹599) is a hypothesis, not a competitor price claim.
- KPI targets are initial targets, not measured.
- Brand name "Slotwise" provisional; trademark/domain/handle checks are owner's.
- Logo to be an original geometric mark; not yet created.
- Host and invitee time zones example: Asia/Kolkata vs America/New_York (DST tests).
- Phase 11 ML module is optional and only after Gate 3 passes + owner says "start Phase 11".

## 8. Risks (PRD §12, Impl Plan §11)
| Risk | Impact | Mitigation |
|---|---|---|
| Double booking | Critical | Atomic transaction, GiST exclusion constraint, concurrency tests (≥50 parallel) |
| DST/time-zone errors | High | IANA zones, UTC storage, DST boundary tests |
| Weak differentiation | High | User interviews and task testing (owner's) |
| DB decision unresolved | High | Gate 0 confirmation of D-01 |
| Email deliverability | Medium | SPF/DKIM/DMARC, retries, bounce monitoring |
| Vercel limits | Medium | Verify limits; fallback Render/Railway |
| No real user data | Medium | Label synthetic data; do not claim real-world performance |

## 9. Proposed task breakdown (Phase 0 deliverables)
1. ✅ Read all 7 PDFs.
2. ✅ Write `docs/00_ANALYSIS.md` (this file).
3. Write `docs/DECISIONS.md` (D-01..D-10 + conflicts).
4. Write `docs/PROGRESS.md`.
5. Scaffold monorepo: dirs, package.json workspaces, .gitignore, .env.example, docker-compose.yml, AGENTS.md, README.md (basic), CI workflow, placeholder app/package manifests.
6. Git init + initial commit.
7. **GATE 0**: report + ask owner to confirm D-01 (PostgreSQL) and D-07 (hosting).

## 10. Open questions for owner (GATE 0)
1. Confirm D-01: PostgreSQL (vs MongoDB) for production.
2. Confirm D-07: Vercel serverless for API with cron worker route, OR Render/Railway.
3. Confirm whether to proceed with Phase 0 scaffolding only (no M0) until approval.