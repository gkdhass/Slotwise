# GAPS.md — everything that is not fully met, and what happens next

Companion to `docs/PARITY.md` (scores) and `docs/TRACEABILITY.md` (evidence).
A gap is recorded here whether or not it blocks release. Nothing is omitted to
protect the score.

Status values: **open** (not fixed), **fixed** (fixed during M7, evidence cited),
**accepted** (decision recorded in `docs/DECISIONS.md`), **blocked** (needs the
owner).

## 1. Open gaps

| ID | Gap | Requirement / evidence | Severity | Plan | Owner action |
| --- | --- | --- | --- | --- | --- |
| G-01 | **M8 rebrand sweep not started.** Implementation Plan traceability row 16 ("Independent rebrand", S01–S11) is the only matrix row with no delivery. | Matrix row 16; `docs/TRACEABILITY.md` §1 | Medium (not a functional requirement) | M8 milestone: replace placeholder brand strings/marks, sweep tokens, re-run the a11y and E2E suites | Authorise M8 at Gate 5 |
| G-02 | **Paid bookings not built** (FR-10, priority *could*). | FR-10; D-08 (`PAYMENTS_ENABLED=false`) | Low (deliberately out of scope) | Reasoned deferral: payments were excluded at Gate 0 (D-08) and the PRD marks them *could*. Re-open only if the report needs a payments chapter | Confirm the deferral stands |
| G-03 | **NFR-02 is only partly proven.** Automated axe + contrast + keyboard + reflow pass, but no manual WCAG 2.2 AA audit and no screen-reader pass; Chromium only. | `tests/e2e/a11y.spec.ts`; `docs/TEST_REPORT.md` §7 | **High** (it is a *must*) | Fix plan (≈3 h): run the WCAG 2.2 AA checklist by hand on S01–S11, do one NVDA (Windows) pass over the booking loop, record findings and fixes in `docs/TEST_REPORT.md` §7. Do this in M8 so the rebrand is audited too | None (agent work), but a screen-reader pass needs ~30 min of a human to sanity-check |
| G-04 | **NFR-04 retention is policy, not enforcement.** No scheduled purge of old cancelled bookings; `docs/PRIVACY.md` §5 says so. | `docs/PRIVACY.md` §5; `accountDeletion.test.ts` | **High** (it is a *must*) | Fix plan (≈2 h): worker job that deletes `status='canceled'` bookings older than a configured window, with an integration test and a `PRIVACY.md` update | Decide the retention window (e.g. 30/90 days) — a privacy decision, not a technical one |
| G-05 | **Neon unverified; NFR-01 not measured against Neon.** All results are local PostgreSQL 18.3 over loopback. | DEV-13; `docs/TEST_REPORT.md` §9.4, §11 | **Blocker for M10** | Blocked on credentials: paste the Neon direct URL, run `pnpm verify:neon` (6 steps), then re-run `pnpm perf` against Neon and replace §9.4's numbers | Provide `DATABASE_URL` |
| G-06 | **CI has never executed.** The 7-job workflow is committed; no GitHub run observed. | `docs/TEST_REPORT.md` §10 | **High** (release gate) | Push and paste the first run; a red job is fixed, never deleted | Push + paste the result |
| G-07 | **FR-09 setup guidance is not usability-tested.** Conflict recovery is proven; "clear and actionable" setup is asserted. | `core-loop.spec.ts`; FR-09 | Medium | Fix plan: 3–5 participant task test (create → publish → book), record task success and time; feeds the report's evaluation chapter | Recruit participants; the agent can write the script |
| G-08 | **`react-router` 6 → 7 major upgrade deferred.** 2 moderate advisories. | DEV-23; `docs/TEST_REPORT.md` §12 | Low (below the `high` gate) | Reasoned deferral: SPA-only, no SSR, no user-supplied navigation targets; upgrading means touching all 11 screens and re-running the whole E2E suite. Do it after M10, or immediately if any advisory is raised to `high` | None |
| G-09 | **`uuid` moderate advisory (dev-only).** | DEV-23 | Low | Accepted: never imported by runtime code; revisit at M10 | None |
| G-10 | **Browser coverage is Chromium only.** No Firefox/WebKit, no real mobile devices (emulated viewports only). | `playwright.config.ts` (one project) | Medium | Fix plan (≈1 h): add `firefox` and `webkit` projects to the `chromium` spec set and run locally; keep CI on Chromium for runtime | None |
| G-11 | **No coverage percentage is measured.** | — | Low | Reasoned deferral: the suites are requirement-driven (every FR/NFR maps to named tests in `docs/TRACEABILITY.md`); a coverage number would not add evidence for this project | None |
| G-12 | **No PITR / off-host restore drill.** Logical `pg_dump`/`pg_restore` rehearsal only. | `docs/DEPLOYMENT.md` §6–7 | Medium | Deferral: the rehearsal is documented and repeatable; PITR is a hosting feature to be exercised at M10 on the managed database | None until M10 |
| G-13 | **Booking write path is not load-tested.** Only `GET` endpoints are under the NFR-01 profile. | `scripts/load.mjs` | Low | Fix plan (≈1 h): add a write scenario (book then cancel via token) at low concurrency, report p95 separately. Not an NFR, so it stays out of the score | None |
| G-14 | **S12 "flagged activity" (Phase 11) not built.** | A-07, D-10 | Low (optional module) | Blocked by design: Phase 11 starts only if the owner says "start Phase 11" after Gate 3 | Explicit go/no-go |
| G-15 | **Archiving is one-way and invisible.** Archived events vanish from `GET /event-types`; there is no "show archived" filter or unarchive action. | `apps/api/src/routes/eventTypes.ts`; `F01-H2` pins the current behaviour | Low (UX) | Fix plan (≈1 h): add `?includeArchived=true` and a toggle on S02. Not required by FR-02; candidate for M8 polish | None |

## 2. Gaps found during M7 and fixed immediately

These were cheap, so they were fixed rather than listed. All are covered by the
test suite as of this milestone.

| Gap | What was wrong | Fix |
| --- | --- | --- |
| **Archive path untested** | `DELETE /event-types/:id` (archive) had no owner-side test; only a cross-owner 404 was asserted. "Archived events are not exposed publicly" was an untested claim in FR-02/FR-04. | Added `F01-H2` "archiving an event hides it from the public page and the slots API" (`apps/api/tests/integration/flows.test.ts`): 204, `archivedAt` set, public page 404, slots 404, row survives, event leaves the active list. |
| **Booking-list filters untested** | `GET /bookings?status&from&to` was implemented but only the cross-owner scoping was tested — the plan's matrix row 15 named `F03-H1`, which is a cancel test. | Added `F03-H3` "the owner booking list filters by status and date and never leaks another host": both statuses, an inclusive date window, and a second host whose booking must not appear. |
| **Slot-window cap untested at the boundary** | The 31-day cap (DEV-24) was new; only the 62-day message test existed. | Added `F01-E2` (32 and 40 days → 422 with `fieldErrors.to`; exactly 31 days → 200) and updated `timezone.test.ts` to the new limit. |
| **Windowed booking query unproven** | The new filtered query could silently over-filter bookings that started before the window, producing double bookings. | Added `F02-H3`: a 60-minute booking at 09:00 must still hide the 09:30 slot of a 30-minute event in a window starting at 09:30, while the 10:00 slot is offered. |
| **README could not set up a clean clone** | The README's six steps fail at `pnpm db:migrate` (`Environment variable not found: DATABASE_URL`) because the API and Prisma read `apps/api/.env`, not the root `.env`. It also documented Node ≥ 20, had no test instructions, no seed instructions, and listed `docs/TRACEABILITY.md` as "to be produced". | README rewritten (see `docs/README_CHECK.md` for the transcript): both env files, Node ≥ 22, database creation + extensions, migrate, seeds, test commands per suite, ports, docs index. |
| **Stale slot could be selected and carried to checkout (S07)** | Found by a flaky E2E assertion, not by a failing test: `a11y.spec.ts` "slot selector" failed once in six runs at `toHaveAttribute("aria-pressed", "true")`. Root cause was in the product, not the test. `S07SlotSelector` cleared the *list* on a date change only when the new fetch resolved, so the previous day's slot buttons stayed clickable during the load. A click on one of them set `selected`, the new list arrived without that slot, and "Continue" stayed enabled pointing at a time that was no longer on screen — a visitor could reach S08/S09 for the wrong day. | The effect now clears both `slots` and `selected` when the `(slug, date, zone)` query changes, so the visible slots and the selection are always from the same query. Pinned by a new E2E test `S07 drops the previous day's slots and selection when the date changes` (`tests/e2e/public.spec.ts`): after selecting a slot, changing the date must disable Continue, empty the pressed state and match the new day's slot count. |

## 3. Gaps that are limitations of evidence, not of the product

Stated so the report does not overclaim:

- **Single-host MVP.** No teams, no round-robin/collective scheduling, no
  calendar sync (Google/Outlook), no payments, no SMS. These were never in scope.
- **No real users.** Every usability claim is a hypothesis (A-01…A-03).
- **Performance numbers are from one contended laptop.** No dedicated load host,
  no sustained soak test, no memory-growth measurement.
- **Email delivery is not exercised end to end** — no Resend API key was
  available; the outbox, retries and worker are tested, the provider call is not.
- **Backup rehearsal used the same machine and the same PostgreSQL instance.**
