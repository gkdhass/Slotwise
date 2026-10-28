# PARITY.md — requirement register, score and verdict (M7)

Purpose: answer "how much of the planned product actually exists, and is that
enough to ship the MVP?" with arithmetic, not adjectives.

Method is the Implementation Plan's own rule
(`docs/source/06_Implementation_Plan_Professionally_Formatted.pdf` §7):

- every functional and non-functional requirement from `docs/00_ANALYSIS.md` §1;
- priority **must = 3**, **should = 2**, **could = 1**;
- score **pass = 1.0**, **partial = 0.5**, **fail = 0**;
- weighted score = achieved points ÷ total points × 100;
- verdict: **not shippable** if any *must* fails, a critical security/integrity
  issue is open, or the score is below 80 %.

Partial is used where a requirement is **only partly proven**, not where it is
merely imperfect. Every row names the evidence; nothing is scored on intention.

## 1. Register and scores

| ID | Requirement (short) | Priority | Weight | Score | Points | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| FR-01 | Register, verify email, log in/out | must | 3 | 1.0 | 3.0 | `F00-H1`, `F00-N1` (`apps/api/tests/integration/flows.test.ts`); `auth.test.ts` (7 tests: verify, duplicate email, weak password, unverified login, session revocation, reset flow); `security.test.ts` CSRF on auth |
| FR-02 | Create/edit/archive event type | must | 3 | 1.0 | 3.0 | `F01-H1` (create + publish), `F01-H2` (archive → 404 publicly, row survives), `F01-N1` (cross-owner), `F01-E1` (invalid duration/range) |
| FR-03 | Weekly availability + time zone | must | 3 | 1.0 | 3.0 | `F01-E1`; `timezone.test.ts` (7: DST spring/fall, host≠invitee zone, invalid zone → 422, pinned clock); `packages/shared/src/slots.test.ts` (9) |
| FR-04 | Visitor views published event and slots | must | 3 | 1.0 | 3.0 | `F01-H1`, `F01-H2` (archived and unpublished are 404), `F02-N1` (draft → 404), `public.spec.ts` (S06/S07 render real data) |
| FR-05 | Book without an account | must | 3 | 1.0 | 3.0 | `F02-H1` (one booking, one token, one outbox job), `F02-N1`, `core-loop.spec.ts` end-to-end booking |
| FR-06 | No overlapping confirmed bookings per host, across event types | must | 3 | 1.0 | 3.0 | `bookings/concurrency/booking.test.ts` "50 parallel requests … exactly one confirmed booking" and "overlapping slots across two event types → at most one"; `bookings_no_host_overlap` EXCLUDE; `verify:constraint` probe |
| FR-07 | Booking confirmation + email queued | must | 3 | 1.0 | 3.0 | `F02-H1` (outbox row asserted inside the booking transaction); `outbox.test.ts` (5: rollback leaves nothing, send once, exponential backoff, not-yet-due jobs, worker secret). *Delivery to a real provider is not exercised — no Resend key — but "queued" is the requirement and is proven.* |
| FR-08 | Cancel / reschedule via secure token | should | 2 | 1.0 | 2.0 | `F03-H1`, `F03-H2`, `F03-E1`, `F03-N1` (identical denial for invalid/expired tokens, no data leaked); `core-loop.spec.ts` reschedule + cancel |
| FR-09 | Clear, actionable setup and conflict messages | should | 2 | **0.5** | 1.0 | Conflict recovery **is** proven (`core-loop.spec.ts` "a taken slot returns to slot selection with the invitee input preserved"; `fieldErrors` asserted in `F00-E1`, `F01-E1`, `F02-N1`). "Clear and actionable" setup guidance is implemented (`S03`–`S05`) but **not measured** — no usability test, no task-success metric. Half proven, half asserted. |
| FR-10 | Paid bookings | could | 1 | **0.0** | 0.0 | Not built by decision D-08 (`PAYMENTS_ENABLED=false`). Gap G-02. |
| NFR-01 | Read API p95 < 500 ms | must | 3 | 1.0 | 3.0 | `docs/TEST_REPORT.md` §9.4: `/slots` p95 **184.6 / 212.0 / 210.7 ms** and `/public/:slug` **59.5 / 61.7 / 65.9 ms**, 3 consecutive runs, 0 errors/timeouts. Caveat: loopback to local PostgreSQL 18.3 — Neon latency excluded and re-measured at M10 (G-05). |
| NFR-02 | WCAG 2.2 AA, keyboard core loop, axe clean | must | 3 | **0.5** | 1.5 | `tests/e2e/a11y.spec.ts`: axe + contrast on every screen at 390 and 1440 px, keyboard-only core loop, reflow at 390/768/1024/1440 and 200 % zoom; contrast audit 216 + 228 samples, worst 5.18:1. **Not proven:** no manual WCAG 2.2 AA audit, no screen-reader pass (NVDA/VoiceOver), Chromium only. Automated tooling covers ~40 % of AA criteria. |
| NFR-03 | Zero double bookings | must | 3 | 1.0 | 3.0 | `booking.test.ts` (2 concurrency tests, 50 parallel requests), DB EXCLUDE constraint, `F02-E1`, `F03-E1` |
| NFR-04 | Minimal invitee data, retention, deletion path | must | 3 | **0.5** | 1.5 | Data minimisation and deletion are real and tested: `accountDeletion.test.ts` (7), `docs/PRIVACY.md` inventory. **Not proven:** retention is policy + manual operator deletion; there is no scheduled purge job for old cancelled bookings (`docs/PRIVACY.md` §5 states this), and no backup-expiry drill. |
| NFR-05 | Structured logs, request IDs, `/health`, error hook | must | 3 | 1.0 | 3.0 | `observability.test.ts` (4), `logger.test.ts` (5, incl. secret redaction), `requestId.test.ts` (5), `errorMonitor.test.ts` (7), `health.test.ts` (2) |
| NFR-06 | Verified at 390 and 1440 px (also 768/1024) | must | 3 | 1.0 | 3.0 | `a11y.spec.ts` viewport scans at 390/768/1024/1440 and the reflow test |

## 2. Arithmetic

```
MUSTS (13 requirements x weight 3 = 39 points available)
  FR-01 3.0  FR-02 3.0  FR-03 3.0  FR-04 3.0  FR-05 3.0  FR-06 3.0  FR-07 3.0
  NFR-01 3.0  NFR-02 1.5  NFR-03 3.0  NFR-04 1.5  NFR-05 3.0  NFR-06 3.0
  musts achieved = 21.0 (FR) + 15.0 (NFR) = 36.0 / 39

SHOULDS (2 x weight 2 = 4 points available)
  FR-08 2.0  FR-09 1.0  =  3.0 / 4

COULDS (1 x weight 1 = 1 point available)
  FR-10 0.0  =  0.0 / 1

TOTAL   = 36.0 + 3.0 + 0.0 = 39.0 / 44
SCORE   = 39.0 / 44 x 100 = 88.636...% -> 88.6%   (not rounded up)
```

## 3. Verdict

| Rule | Check | Result |
| --- | --- | --- |
| Any *must* fails? | Lowest must score is 0.5 (NFR-02, NFR-04); no must is 0 | **No** |
| Critical security/integrity issue open? | `pnpm audit --audit-level=high` exits 0; 3 moderate accepted with reasoning (DEV-23); no open integrity defect — `bookings_no_host_overlap` is enabled and proven | **No** |
| Score ≥ 80 %? | 88.6 % | **Yes** |

**Verdict: shippable at MVP scope, with conditions.** The product meets its
must-haves, its double-booking invariant is enforced in the database and proven
under concurrency, and the parity score is 88.6 %.

The conditions are process conditions, not requirement failures:

1. **Neon verification** (`pnpm verify:neon` 6/6 against a Neon host) — hard
   blocker before M10 (DEV-13).
2. **CI must actually run** — the 7-job workflow has never executed on GitHub.
3. **M8 rebrand sweep** (Implementation Plan matrix row 16) — not started.
4. NFR-01 must be re-measured against Neon before the number is quoted as a
   production result.

## 4. What would move the score

| Change | Points | New score |
| --- | --- | --- |
| Add a manual WCAG 2.2 AA review + one screen-reader pass (NFR-02 → 1.0) | +1.5 | 92.0 % |
| Add a scheduled purge job for old cancelled bookings (NFR-04 → 1.0) | +1.5 | 95.5 % |
| Usability-test the setup guidance with 3–5 tutors (FR-09 → 1.0) | +1.0 | 97.7 % |
| Implement payments (FR-10 → 1.0) | +1.0 | 100 % |

Only the first two are in the project's own control; the third needs
participants, the fourth is out of scope by decision.

## 5. Reproducing the evidence

```bash
pnpm test:unit          # 40
pnpm test:integration   # 48
pnpm test:security      # 16
pnpm test:concurrency   # 2
pnpm test:e2e --retries=0  # 16
pnpm perf --autocannon  # 3 runs, docs/TEST_REPORT.md §9.4
pnpm audit --audit-level=high
```
