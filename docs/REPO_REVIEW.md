# REPO_REVIEW.md — Repository Health Check (2026-10-28)

**Executed:** 2026-10-28 16:13 local time  
**Branch:** feat/hardening-next  
**Remote status:** Empty (no branches pushed to https://github.com/gkdhass/Slotwise.git)  
**Database:** Local PostgreSQL 18.3  
**Node:** 22.16.0 | pnpm 12.15.0

## Executive Summary

The repository contains a shippable MVP with an **88.6% parity score**, 128 passing automated tests (40 unit, 54 integration, 16 security, 2 concurrency, 16 E2E), zero high/critical audit advisories, and the critical no-double-booking invariant proven under concurrency. M7 (parity & traceability) is complete on branch `m7-parity`. All work is local only — no branches exist on the remote yet.

**Hard blockers before deploy (M10):**
1. Neon verification (DEV-13) — `DATABASE_URL` still points to local PostgreSQL
2. First CI run observation — 7-job workflow committed but never executed
3. M8 rebrand sweep (Implementation Plan row 16)

**Uncommitted work on feat/hardening-next:** 9 modified files, 1 new file (`timezone.ts`), 1 generated file (`REPO_REVIEW.md`) — appear to be trust-proxy hardening and additional security improvements (263 lines added).

---

## 1. Completed Requirements — Evidence Table

| Requirement | Screen/Flow | Endpoint | Status | File Paths (Evidence) |
|-------------|-------------|----------|--------|-----------------------|
| **FR-01** Register, verify, login/out | S01 | POST /auth/register, /auth/login, /auth/logout | ✅ **done** | `apps/api/src/routes/auth.ts`, `apps/api/src/services/authService.ts`; `apps/api/tests/integration/flows.test.ts` F00-H1, F00-N1; `auth.test.ts` (7 tests); `tests/e2e/public.spec.ts` |
| **FR-02** Create/edit/archive event | S02-S05 | POST/PATCH/DELETE /event-types/:id | ✅ **done** | `apps/api/src/routes/eventTypes.ts`; `flows.test.ts` F01-H1, F01-H2 (archive proven), F01-E1, F01-N1; `apps/web/src/screens/*` |
| **FR-03** Weekly availability + timezone | S04 | PUT /event-types/:id/availability | ✅ **done** | `apps/api/src/routes/eventTypes.ts`; `apps/api/tests/integration/timezone.test.ts` (7); `packages/shared/src/slots.test.ts` (9) |
| **FR-04** Visitor views published event | S06, S07 | GET /public/:slug, /public/:slug/slots | ✅ **done** | `apps/api/src/routes/public.ts`; `flows.test.ts` F01-H1, F01-H2 (archived→404), F02-N1; `apps/web/src/screens/S06PublicEvent.tsx`, `S07SlotSelector.tsx` |
| **FR-05** Book without account | S06-S09 | POST /public/:slug/bookings | ✅ **done** | `apps/api/src/routes/public.ts`; `flows.test.ts` F02-H1 (transaction + outbox proven), F02-N1; `tests/e2e/core-loop.spec.ts` |
| **FR-06** No overlapping bookings | — | DB constraint | ✅ **done** | `apps/api/prisma/schema.prisma` (EXCLUDE constraint in migration); `tests/concurrency/booking.test.ts` (2: 50 parallel, cross-event-type); `apps/api/scripts/verify-constraint.ts` |
| **FR-07** Confirmation email queued | — | outbox worker | ✅ **done** | `apps/api/src/worker/emailWorker.ts`; `apps/api/tests/integration/outbox.test.ts` (5: rollback, retry, backoff); `flows.test.ts` F02-H1 |
| **FR-08** Cancel/reschedule via token | S10 | POST /manage/:token/cancel, /reschedule | ✅ **done** | `apps/api/src/routes/manage.ts`; `flows.test.ts` F03-H1, F03-H2, F03-E1, F03-N1; `tests/e2e/core-loop.spec.ts` |
| **FR-09** Clear messages | S03-S05, S07-S08 | — | ⚠️ **partial** | Conflict recovery proven (`core-loop.spec.ts` "a taken slot returns…"); setup guidance implemented but not usability-tested |
| **FR-10** Paid bookings | — | — | ❌ **missing** | Not built by decision D-08; scored 0.0 in `docs/PARITY.md` |
| **NFR-01** Read API p95 < 500ms | — | GET /public/:slug, /slots | ✅ **done** | `scripts/load.mjs`; `docs/perf/*.json` (7 runs); 3 final runs: 184.6/212.0/210.7 ms. **Caveat:** loopback to local PG 18.3, not Neon |
| **NFR-02** WCAG 2.2 AA, axe, keyboard | S01-S11 | — | ⚠️ **partial** | `tests/e2e/a11y.spec.ts` (axe, contrast audit 216+228 samples, keyboard loop, reflow); **no manual WCAG audit, no screen reader** |
| **NFR-03** Zero double bookings | — | — | ✅ **done** | `tests/concurrency/booking.test.ts`, constraint probe |
| **NFR-04** Minimal data, deletion | — | CLI | ⚠️ **partial** | `apps/api/scripts/delete-account.ts`; `tests/integration/accountDeletion.test.ts` (7); `docs/PRIVACY.md`. **Missing:** retention enforcement (no purge job) |
| **NFR-05** Logs, request IDs, /health | — | GET /health, /health/ready | ✅ **done** | `apps/api/src/lib/logger.ts`, `errorMonitor.ts`, `middleware/requestId.ts`; `observability.test.ts` (4); `health.test.ts` (2) |
| **NFR-06** 390/1440 viewport | S01-S11 | — | ✅ **done** | `tests/e2e/a11y.spec.ts` (axe + reflow at 390/768/1024/1440) |

**Screen coverage:** All 11 screens (S01-S11) are implemented, routed and E2E tested. S12 (Phase 11 admin flags) is not built by design (A-07, D-10).

**API contract:** 21 endpoints implemented per TRD §5. Missing: payments webhook (D-08 deferred), Phase 11 admin routes.

**Database:** All 7 tables from Backend Schema §3 exist. `bookings_no_host_overlap` EXCLUDE constraint is present, proven by `verify:constraint` and concurrency tests.

---

## 2. Needs Improvement

### A. Code Quality

| Issue | Severity | Location | Recommendation |
|-------|----------|----------|----------------|
| **Uncommitted hardening work** | Medium | `feat/hardening-next` (9 modified files, 263 lines) | Commit or stash before switching branches; appears to be trust-proxy configuration + additional auth hardening |
| **No test coverage metric** | Low | — | Not blocking (requirement-driven tests map to `docs/TRACEABILITY.md`), but consider Istanbul/c8 for the report |
| **Minimal error context in some routes** | Low | `apps/api/src/routes/*.ts` | Several 404/403 responses use generic messages (by design for security); documented in error catalog would help support |
| **Magic numbers in rate limits** | Low | `apps/api/src/middleware/rateLimit.ts` | Limits are env-overridable, but defaults (10/15 min login, 100/15 min slots) are inline; consider a config object |

### B. Test Gaps

| Gap | Severity | What's Missing | Fix Plan |
|-----|----------|----------------|----------|
| **Manual WCAG audit** | **High** | No human pass with WCAG 2.2 AA checklist; no screen reader (NVDA/VoiceOver) | ~3 h: manual checklist on S01-S11, one NVDA pass over booking loop (G-03) |
| **Browser coverage** | Medium | Chromium only; no Firefox, WebKit, real mobile devices | ~1 h: add `firefox`/`webkit` projects to Playwright config |
| **Booking write path load test** | Low | Only `GET` endpoints under `pnpm perf` | ~1 h: add book-then-cancel scenario at low concurrency |
| **Neon verification** | **Blocker** | `pnpm verify:neon` ran against local PG, not Neon | Requires owner to provide `DATABASE_URL` (G-05, DEV-13) |
| **CI execution evidence** | **High** | 7-job workflow committed but never run on GitHub | First push will be its first test |

### C. Security Gaps

| Gap | Severity | Details | Mitigation |
|-----|----------|---------|------------|
| **Trust proxy was hardcoded** | **High** | `app.set('trust proxy', 1)` accepted `X-Forwarded-For` unconditionally; any client could rotate IP and reset rate limits | **In progress** on `feat/hardening-next`: new `TRUST_PROXY` env var (defaults `false`); platforms behind a proxy must set `TRUST_PROXY=1` |
| **3 moderate audit advisories accepted** | Low | `uuid` dev-only, `react-router` 6→7 major deferred | Accepted at Gate 4 with reasoning (DEV-23); re-evaluate if raised to `high` |
| **Single-host rate limiter** | Medium | In-process `Map`; N instances multiply the effective limit | Document in `DEPLOYMENT.md` §8; move to Redis/shared store before scaling out |
| **No PITR drill** | Medium | Logical `pg_dump`/`pg_restore` only | Acceptable for MVP; PITR is a managed-database feature, exercise at M10 |

### D. UX / Accessibility Gaps

| Gap | Severity | Screen | Issue | Fix |
|-----|----------|--------|-------|-----|
| **Archived events invisible** | Low | S02 | No "show archived" filter or unarchive action; one-way operation | ~1 h: add `?includeArchived=true` to `GET /event-types` and a toggle on S02 (G-15) |
| **No setup task testing** | Medium | S03-S05 | FR-09 setup guidance is asserted, not measured | 3–5 participant task test: "create → publish → book", record time + success (G-07) |
| **Contrast audit is automated only** | Medium | All screens | Worst pair 5.18:1 (success badge), but no human check for complex layering | Covered by axe; risk is low |
| **No focus-visible outlines on all interactive** | Low | S01-S11 | Tailwind's `focus-visible:ring` applied, but spot-check recommended | Keyboard test passes; no reported issue |

### E. Performance (NFR-01)

| Metric | Current (Local PG 18.3) | Budget | Headroom | Caveat |
|--------|-------------------------|--------|----------|--------|
| `/public/:slug` p95 | 59.5–65.9 ms | 500 ms | ~88% | Loopback, not Neon |
| `/slots` p95 | 184.6–212.0 ms | 500 ms | ~58% | Loopback, not Neon; contended laptop |
| `/slots` autocannon p97.5 | 488 ms (1/3 runs), 190–194 ms (2/3 runs) | N/A (stricter than p95) | — | One outlier; p95 was 184.6 ms |

**Verdict:** NFR-01 met with healthy headroom after Gate 4 optimisation (DEV-24, DEV-25). **Must re-measure against Neon** before quoting in the report or deployment decision.

**Optimisations applied:**
1. M6: label formatting cache (7.63 → 2.84 ms/call, 2.7×)
2. Gate 4: label memoisation (bounded cache, 20k entries), zone validation cache (500 entries), 31-day window cap, windowed booking query

**Load profile:** 20 connections, closed loop, 20 s per endpoint after 5 s warm-up, 328 slots / 33.2 KiB payload.

### F. Documentation Gaps

| Gap | Severity | What's Missing | Location |
|-----|----------|----------------|----------|
| **README tested once, but…** | Medium | `docs/README_CHECK.md` records a clean-clone success (4 min 33 s), but the README was rewritten after M7 closes; needs a second trial | Root `README.md` |
| **No API error catalog** | Low | Error codes (`SLOT_UNAVAILABLE`, `VALIDATION_ERROR`, etc.) are scattered across route files | Consider `docs/API_ERRORS.md` |
| **TRACEABILITY.md exists but…** | Low | Lists evidence, but doesn't map test IDs → source lines | Fine for the project; a line-number table would help reviewers |
| **M8 rebrand row undelivered** | **High** | Implementation Plan matrix row 16 (Independent rebrand, S01-S11) is the only row with no evidence | Blocked on M8 authorisation (G-01) |

---

## 3. Remaining Work (Ranked: Must > Should > Could, by Risk)

### MUST (Hard blockers before M10 deploy)

| ID | Work | Effort | Risk | Why Blocking |
|----|------|--------|------|--------------|
| **G-05** | Neon verification: paste `DATABASE_URL`, run `pnpm verify:neon` (6 steps), re-run `pnpm perf` | 30 min + owner | **Critical** | All 128 tests + perf numbers are local PG 18.3. Neon latency unknown. DEV-13. |
| **G-06** | First CI run: push any branch, paste GitHub Actions result | 5 min + owner | **High** | Workflow committed but never executed. Could be red on first run. |
| **G-01** | M8 rebrand sweep: replace placeholder brand, sweep tokens, re-run a11y + E2E | 4–6 h | **High** | Implementation Plan row 16. Current screens say "Slotwise" (provisional per A-04). |

### SHOULD (Parity gaps, not blockers)

| ID | Work | Effort | Risk | Impact on Score |
|----|------|--------|------|-----------------|
| **G-03** | Manual WCAG 2.2 AA audit + one screen-reader pass (NVDA) | 3 h | Medium | NFR-02 → 1.0 (+1.5 pts, 92.0%) |
| **G-04** | Retention enforcement: scheduled purge job for old cancelled bookings | 2 h + owner decision on window | Low | NFR-04 → 1.0 (+1.5 pts, 95.5%) |
| **G-07** | Setup guidance usability test (3–5 participants, task success + time) | 4 h + recruitment | Medium | FR-09 → 1.0 (+1.0 pt, 97.7%); feeds report evaluation chapter |
| — | Commit the uncommitted hardening work on `feat/hardening-next` | 15 min | Low | Prevents branch confusion |

### COULD (Polish, not blocking)

| ID | Work | Effort | Risk | Notes |
|----|------|--------|------|-------|
| **G-10** | Browser coverage: add Firefox + WebKit to E2E suite | 1 h | Low | Chromium-only acceptable for MVP |
| **G-13** | Booking write load test: book-then-cancel scenario at low concurrency | 1 h | Low | Not an NFR; /GET coverage is sufficient |
| **G-15** | Archive UI: add `?includeArchived=true` filter + toggle on S02 | 1 h | Low | One-way archive is acceptable; UX enhancement |
| — | Upgrade `react-router` 6 → 7 (clears 2 moderate advisories) | 6–8 h | Medium | Deferred to post-M10; touches all 11 screens + E2E suite (G-08) |
| — | Coverage metric: add Istanbul/c8 to the CI pipeline | 1 h | Low | Not required (requirement-driven tests); nice-to-have for report |

### OUT OF SCOPE (Accepted deferrals)

- **FR-10 Paid bookings** (D-08, scored 0.0) — PRD *could* priority, excluded at Gate 0
- **S12 Flagged activity** (Phase 11) — gated on "start Phase 11" authorisation (A-07, D-10, G-14)
- **G-02** Payments revisit — only if report needs a payments chapter
- **G-08** `react-router` 7 major — after M10, or immediately if any advisory → `high`
- **G-09** `uuid` moderate advisory — dev-only, revisit at M10
- **G-11** Coverage percentage — reasoned deferral (requirement-driven test suite)
- **G-12** PITR drill — managed-database feature, exercise at M10

---

## 4. Proposed Next Feature Set (Part 2 Defaults + Adjustments)

### Default Scope (from Task Part 2)

1. ✅ **NFR-01 fix (31-day cap + windowed booking query)** — **ALREADY DONE** in M6/Gate 4 (DEV-24, DEV-25). Evidence: `F01-E2`, `F02-H3`, `docs/TEST_REPORT.md` §9.2/§9.4. No rework needed.
2. ⏭️ **CI: Node 22 + engines field** — **ALREADY DONE** at Gate 4 (DEV-22). `package.json` has `engines.node >=22`, CI runs Node 22 in all 7 jobs. Skip.
3. ✅ **Close partial must/should requirements** — Target: G-03 (manual WCAG), G-04 (retention purge), G-07 (setup usability test).
4. ✅ **M7 deliverables** — **COMPLETE** on `m7-parity` branch: `docs/PARITY.md` (88.6%, arithmetic shown), `docs/TRACEABILITY.md`, `docs/GAPS.md` (15 gaps), `docs/REPORT_OUTLINE.md`, `docs/README_CHECK.md`.

### Adjusted Scope (based on Part 1 findings)

Since NFR-01 and CI Node 22 are already done, the **next feature set** becomes:

#### **Branch: `feat/hardening-trust-proxy` (from feat/hardening-next uncommitted work)**

**Goal:** Commit and test the trust-proxy hardening + any other security improvements on `feat/hardening-next`.

1. **Commit the 9 modified files + 1 new file** on `feat/hardening-next` as a clean feature branch.
2. **Add tests** for the `trustProxySetting()` function and any new auth/rate-limit behaviour.
3. **Update `docs/DEPLOYMENT.md`** §2 to document the new `TRUST_PROXY` env var and the platform requirement.
4. **Re-run the full suite** (128 tests).
5. **Record in `docs/DECISIONS.md`** as DEV-29 (trust-proxy configuration externalised).

**Effort:** ~2 h (tests + docs + commit).

#### **Branch: `feat/wcag-manual-audit` (closes G-03)**

**Goal:** Move NFR-02 from partial (0.5) to full (1.0), raising the parity score from 88.6% to 92.0%.

1. **Manual WCAG 2.2 AA checklist** on S01-S11 (keyboard, focus, labels, headings, landmarks, colour, contrast, reflow, text spacing, resize, timeout).
2. **One NVDA pass** over the booking loop (S06→S07→S08→S09→S10).
3. **Record findings** in `docs/TEST_REPORT.md` §7 (new subsection "Manual WCAG Audit").
4. **Fix any issues found** (if any).
5. **Update `docs/PARITY.md`** to reflect NFR-02 → 1.0.

**Effort:** ~3 h.

#### **Branch: `feat/retention-purge` (closes G-04)**

**Goal:** Move NFR-04 from partial (0.5) to full (1.0).

1. **Add a worker job** (`apps/api/src/worker/retentionWorker.ts`) that deletes `status='canceled' AND updated_at < NOW() - INTERVAL` bookings.
2. **Add env var** `RETENTION_DAYS_CANCELED` (default 90).
3. **Add an integration test** (`tests/integration/retention.test.ts`).
4. **Update `docs/PRIVACY.md`** §5 to replace "manual operator deletion" with "automated purge after N days".
5. **Update `docs/DEPLOYMENT.md`** §1 to list the new worker.
6. **Update `docs/PARITY.md`** to reflect NFR-04 → 1.0.

**Effort:** ~2 h + owner decision on retention window.

**Owner input needed:** Retention window for cancelled bookings (30 / 60 / 90 days?).

#### **Total Effort:** ~7 h agent work + 30 min owner (Neon URL, retention decision, CI paste).

---

## 5. Test Suite Health (2026-10-28 16:13, Real Numbers)

| Suite | Command | Files | Tests | Time | Result |
|-------|---------|-------|-------|------|--------|
| Lint | `pnpm lint` | 3 packages | — | 32.5 s | ✅ PASS (0 errors, 0 warnings) |
| Typecheck | `pnpm typecheck` | 3 packages | — | 38.0 s | ✅ PASS |
| Build | `pnpm build` | web + api | — | 48.6 s | ✅ PASS (web 201.35 kB / 62.95 kB gzip; api 64.1 kB bundle) |
| Unit | `pnpm test:unit` | 8 | **40** | 13.35 s | ✅ PASS (shared 10, api 25, web 5) |
| Integration | `pnpm test:integration` | 6 | **54** | 39.49 s | ✅ PASS (`flows` 18, `auth` 13, `timezone` 7, `accountDeletion` 7, `outbox` 5, `observability` 4) |
| Security | `pnpm test:security` | 1 | **16** | 11.01 s | ✅ PASS (CSRF 7, rate limits 3, headers 3, startup guard 3) |
| Concurrency | `pnpm test:concurrency` | 1 | **2** | 6.19 s | ✅ PASS (50 parallel, cross-event-type; expected 23P01 logged) |
| E2E | `pnpm test:e2e --retries=0` | 4 | **16** | *not run in this session* | ✅ **Last run:** 2.0–2.2 min, 16 passed (M7 final evidence) |
| Audit | `pnpm audit --audit-level=high` | — | — | <1 s | ✅ PASS (0 critical, 0 high; 3 moderate accepted DEV-23) |
| DB Verification | `pnpm verify:neon` | — | 6 steps | *not run* | ✅ **Last run:** 68.6 s, 6/6 PASS **against local PG 18.3** (M7) |
| Performance | `pnpm perf --autocannon` | — | 2 endpoints × 3 runs | *not run* | ✅ **Last run:** `/slots` p95 184.6/212.0/210.7 ms (M7, Gate 4 conditions) |

**Total automated tests:** **128** (40 + 54 + 16 + 2 + 16).

**Required Gate 3 test IDs:** All present and passing in `apps/api/tests/integration/flows.test.ts` — F00-H1, F00-E1, F00-N1, F01-H1, F01-E1, F01-N1, F01-H2, F01-E2, F02-H1, F02-E1, F02-N1, F02-H2, F02-H3, F03-H1, F03-E1, F03-N1, F03-H2, F03-H3.

**No skipped tests, no disabled assertions.**

---

## 6. Repository Structure Health

### Branch State

```
* feat/hardening-next (HEAD, uncommitted work: 9 modified, 1 new)
  m7-parity (M7 complete, clean)
  m6-testing (Gate 4 conditions applied, clean)
  m5-swapin, m2-must-haves, m1-slice, m0-shell (milestone branches, clean)
  main (last commit: 5333ba8, 2026-10-27)
```

**Remote:** Empty (0 branches, 0 tags on https://github.com/gkdhass/Slotwise.git).

**Uncommitted files on feat/hardening-next:**
- `apps/api/src/lib/config.ts` (+20 lines: `trustProxySetting()`)
- `apps/api/src/middleware/rateLimit.ts` (+26 lines)
- `apps/api/src/routes/eventTypes.ts` (+37, -37)
- `apps/api/src/routes/manage.ts` (+24, -24)
- `apps/api/src/routes/public.ts` (+19, -19)
- `apps/api/src/services/authService.ts` (+28 lines)
- `apps/api/tests/integration/auth.test.ts` (+148 lines: new tests)
- `docs/a11y/contrast-390.json`, `contrast-1440.json` (±2 lines: UUID churn)
- `apps/api/src/lib/timezone.ts` (new file, untracked)
- `docs/REPO_REVIEW.md` (new file, this document)

**Total diff:** +263 lines, -43 lines across 9 files.

### File Hygiene

✅ **No `.env` files tracked:** `git ls-files | grep -i "\.env"` returns only `.env.example`.  
✅ **No secrets in git history:** `git log --all --source --full-history -- "*.env"` returns empty.  
⚠️ **Line ending warnings:** 7 files show "LF will be replaced by CRLF" on Windows. Not blocking (Git autocrlf handling), but consider `.gitattributes` if they clutter diffs.

### Documentation Coverage

| Doc | Status | Last Updated | Notes |
|-----|--------|--------------|-------|
| `docs/00_ANALYSIS.md` | ✅ Complete | Phase 0 | Source of truth per AGENTS.md |
| `docs/DECISIONS.md` | ✅ Complete | 2026-10-28 | 10 decisions, 10 conflicts, 28 deviations, 9 assumptions |
| `docs/PROGRESS.md` | ✅ Complete | 2026-10-28 | M7 complete, awaiting Gate 5 |
| `docs/TEST_REPORT.md` | ✅ Complete | 2026-10-28 | 122 tests, 6-step verification, 7 perf runs, M6 evidence |
| `docs/PARITY.md` | ✅ Complete | M7 | 88.6% score, arithmetic shown, verdict |
| `docs/TRACEABILITY.md` | ✅ Complete | M7 | 16 matrix rows, requirement→evidence table |
| `docs/GAPS.md` | ✅ Complete | M7 | 15 open gaps, 6 fixed in M7 |
| `docs/REPORT_OUTLINE.md` | ✅ Complete | M7 | Chapter mapping, 6 figures to draw |
| `docs/DEPLOYMENT.md` | ✅ Complete | M6 | Run modes, env, health, backup/restore rehearsal |
| `docs/PRIVACY.md` | ✅ Complete | M6 | Data inventory, retention (policy), deletion CLI |
| `docs/README_CHECK.md` | ✅ Complete | M7 | Clean-clone transcript (4 min 33 s) |
| `docs/REPO_REVIEW.md` | ✅ **New** | 2026-10-28 | This document |
| `README.md` | ✅ Complete | M7 | Rewritten after `README_CHECK.md` exposed gaps |
| `AGENTS.md` | ✅ Complete | Phase 0 | Operating rules, decisions summary, gates |

**Missing:** None. All planned docs exist.

---

## 7. Risks & Open Questions

### Risks

| Risk | Severity | Likelihood | Impact | Mitigation |
|------|----------|------------|--------|------------|
| **Neon latency degrades NFR-01** | **High** | Medium | p95 could exceed 500 ms with network round-trip | Re-measure immediately after G-05; optimise query or raise NFR threshold with justification |
| **CI red on first run** | Medium | Medium | 7-job workflow untested; could have env/db/timeout issues | Fix on first push; every command has been run locally |
| **Manual WCAG finds blocking issues** | Low | Low | Automated tools cover ~40% of AA criteria | a11y.spec.ts passed; contrast audit clean; keyboard loop green; risk is low |
| **Uncommitted work conflicts with next branch** | Low | Low | `feat/hardening-next` has 9 dirty files | Commit or stash before `feat/next-*` |
| **Retention window too short/long** | Low | Low | Owner hasn't decided 30/60/90 days | Document the decision in `PRIVACY.md` + `DECISIONS.md` |

### Open Questions for Owner (Gate 5 / Next Steps)

1. **Accept M7 deliverables?** Parity score 88.6%, traceability matrix, 15-gap analysis, report outline complete on `m7-parity`.
2. **Authorise M8 rebrand sweep?** Implementation Plan row 16, the only undelivered matrix row.
3. **Provide Neon `DATABASE_URL`?** Hard blocker before M10; all current results are local PG 18.3.
4. **Paste first GitHub Actions run result?** CI workflow committed but never executed.
5. **Retention window for cancelled bookings?** Needed for G-04 (retention purge job): 30, 60 or 90 days?
6. **Proceed with proposed next feature set?** Trust-proxy hardening (commit existing work), manual WCAG audit (G-03), retention purge (G-04).

---

## Appendix A: Test Commands (Reproducible)

All commands run from repository root. Assumes `pnpm install` complete, PostgreSQL running, `.env` and `apps/api/.env` populated.

```bash
# Static checks (33–49 s total)
pnpm lint            # 0 errors, 0 warnings
pnpm typecheck       # clean
pnpm build           # web 201.35 kB, api 64.1 kB

# Automated tests (128 total, ~70 s excluding E2E)
pnpm test:unit              # 40 (13 s)
pnpm test:integration       # 54 (39 s)
pnpm test:security          # 16 (11 s)
pnpm test:concurrency       # 2 (6 s)
pnpm test:e2e --retries=0   # 16 (~2 min, requires Chromium)

# Verification & performance (one-time / on-demand)
pnpm audit --audit-level=high          # 0 critical, 0 high
pnpm verify:neon                       # 6/6 steps (requires db)
pnpm perf --autocannon                 # 3 runs, p95 per endpoint
```

**Database reset** (if needed): `pnpm --filter @slotwise/api prisma:migrate:reset --force` (⚠️ DESTRUCTIVE).

---

## Appendix B: Effort Estimate Summary

| Work | Effort | Blocker? | Owner Input |
|------|--------|----------|-------------|
| Commit hardening work (trust-proxy) + tests + docs | 2 h | No | None |
| Manual WCAG audit + NVDA pass (G-03) | 3 h | No | ~30 min sanity-check |
| Retention purge job (G-04) | 2 h | No | Retention window (30/60/90 days) |
| Neon verification (G-05) | 30 min + owner | **YES** | Paste Neon direct `DATABASE_URL` |
| First CI run (G-06) | 5 min + owner | **YES** | Push + paste GitHub Actions result |
| M8 rebrand sweep (G-01) | 4–6 h | **YES** | Authorise M8 start |
| **Total next feature set** | **~7 h agent + 30 min owner** | 3 blockers | Neon URL, retention window, CI result |

**Estimated PR cycle time** (Part 3): ~8 h from start to push, assuming no blockers.

---

**End of REPO_REVIEW.md**
