# REPORT_OUTLINE.md — mapping repo artefacts to the final-year report

How to turn this repository into the report, chapter by chapter. For each chapter:
what the artefact is, where it lives, which figures/tables to reuse, and what
**you** still have to write yourself (the parts that are argument, reflection or
context, which no artefact can supply).

Everything in the "reuse" column already exists and is measured. Nothing in this
document is a promise of results — if a number is not in the cited file, it does
not exist yet.

---

## 1. Introduction

| | |
| --- | --- |
| Reuse | `docs/00_ANALYSIS.md` §1 (problem framing), §7 (assumptions), §8 (risks); `README.md` "Status" for what was built |
| Figures/tables | Table: scope in/out (must/should/could register from `docs/PARITY.md` §1) |
| You must write | Motivation and the local context (why single-host scheduling, why this project, your aims and objectives), the report's own contribution statement, and a paragraph that frames every persona/pain point as a **hypothesis** (A-01…A-03), not a finding |

Do **not** copy the IEEE paper's threat-detection framing — it is a different
domain (C-05/C-09). Phase 11 is optional and advisory only.

## 2. Literature review

| | |
| --- | --- |
| Reuse | `docs/00_ANALYSIS.md` §6 (cross-document conflicts), `docs/source/` (the six planning PDFs and their source register, Implementation Plan §13) |
| Figures/tables | Table: source register with what each source supports and its limitation (`06_Implementation_Plan` §13) |
| You must write | The actual review: scheduling/booking literature, time-zone and DST handling, WCAG 2.2, exclusion constraints or equivalent integrity techniques, and a critical comparison of 3–5 existing tools. This is the chapter with the least support in the repo — plan for real reading time |

The repo gives you a clean-room constraint (no copied assets or copy) but not a
literature survey.

## 3. Requirements

| | |
| --- | --- |
| Reuse | `docs/00_ANALYSIS.md` §1 (FR-01…FR-10, NFR-01…NFR-06 with priorities), §2 (S01–S12), §3 (F00–F03), §4 (API inventory), §5 (database inventory) |
| Figures/tables | Requirements table (ID, statement, priority, acceptance criterion); screen inventory; flow inventory |
| You must write | The requirements-engineering narrative: how you elicited them, the MoSCoW rationale, and traceability from objectives → requirements. State plainly that the requirements were derived from documents and hypotheses, not interviews (unless you run G-07) |

## 4. Design

| | |
| --- | --- |
| Reuse | `docs/00_ANALYSIS.md` §5 (schema), `apps/api/prisma/schema.prisma` (authoritative), `docs/TRACEABILITY.md` §3 (screens → routes), `docs/DECISIONS.md` (D-01…D-10, DEV-07…DEV-25) |
| Figures/tables | ER diagram of the 7 tables (draw from the schema); architecture diagram (SPA → API → PostgreSQL + outbox worker); sequence diagram of the booking transaction (see below); API route table (`docs/TRACEABILITY.md` §1); screen map |
| You must write | Design rationale prose: why a server-authoritative slot generator, why the exclusion constraint instead of application-level locking, why server sessions + Argon2id + CSRF rather than JWT, why the outbox pattern. Also the UI/UX section: tokens, layout, accessibility decisions |

**Sequence diagram to draw** (the single most important design figure). The
transaction order is fixed in the code (`apps/api/src/routes/public.ts`): validate
request → load event type → compute slots → begin transaction → insert booking →
insert management token → insert outbox job → commit → respond. Say explicitly
that the email is sent **after** commit by a worker that claims jobs with
`FOR UPDATE SKIP LOCKED`, and that `bookings_no_host_overlap` (GiST EXCLUDE,
partial on `status='confirmed'`) is what makes double booking impossible rather
than unlikely.

## 5. Implementation

| | |
| --- | --- |
| Reuse | `apps/api/src/**`, `apps/web/src/**`, `packages/shared/src/slots.ts`, `apps/api/prisma/migrations/`, `README.md` (setup), `docs/DEPLOYMENT.md` |
| Figures/tables | Module/package table (repo layout from `README.md`); migration list; a short code extract of the slot generator and of the booking transaction; the CPU profile table from `docs/TEST_REPORT.md` §9.2 |
| You must write | Implementation narrative and reflection: what you built, the order you built it, the deviations you hit (DEV-01…DEV-25 give you the material — pick the 5–8 that mattered), and the engineering trade-offs you now think were right or wrong |

Do not paste whole files. Two short extracts (slot generation, booking
transaction) plus the migration list is enough; the report is not the codebase.

## 6. Testing

| | |
| --- | --- |
| Reuse | `docs/TEST_REPORT.md` (all of it), `docs/TRACEABILITY.md` §2, `docs/perf/*.json`, `docs/a11y/*.json`, `.github/workflows/ci.yml` |
| Figures/tables | Suite results table (122 tests: 40 unit / 48 integration / 16 security / 2 concurrency / 16 E2E); requirement → test table; NFR-01 three-run table; the two failed perf runs (§9.3) as evidence of measurement discipline; axe/contrast summary |
| You must write | Test strategy narrative: unit vs integration vs E2E, why no mocks at the integration layer, why concurrency tests are not optional here, and an honest discussion of what the suites do **not** cover (G-10, G-11, G-13) |

**Include the two failed runs.** They are the strongest evidence that the
measurements are honest: a 903-second sample in a 20-second window (host stall)
and a contended run at p95 1125 ms, both published next to the passing runs.

## 7. Results

| | |
| --- | --- |
| Reuse | `docs/PARITY.md` (register + arithmetic + verdict), `docs/TEST_REPORT.md` §9.4 (perf), §7 (accessibility), §8 (backup/restore), `docs/GAPS.md` |
| Figures/tables | Parity score table with arithmetic (39.0/44 = 88.6 %); NFR-01 before/after (410.6 → 184.6/212.0/210.7 ms) with the three-run table; accessibility evidence table; backup/restore table |
| You must write | Results discussion: what the numbers mean, which requirement is best and worst served, and the comparison against the *targets* (not against competitors — there is no competitor data, A-01/A-02) |

If you run the participant task test (G-07), its results belong here and would
also raise FR-09 from partial to pass.

## 8. Limitations

| | |
| --- | --- |
| Reuse | `docs/GAPS.md` §1 and §3, `docs/TEST_REPORT.md` §9.1 caveats, §11 (Neon), §14 |
| Figures/tables | Gap table with severity and plan |
| You must write | The reflective part: what you would do differently, what the project cannot claim (no real users, one contended laptop, Chromium only, no Neon latency, partial WCAG and retention), and the threat-to-validity discussion |

This chapter is where NFR-02/NFR-04 being *partial* must be stated plainly. A
report that claims full WCAG compliance from axe scans alone would be wrong.

## 9. Conclusion and future work

| | |
| --- | --- |
| Reuse | `docs/PARITY.md` §4 ("what would move the score"), `docs/GAPS.md` (plans), `docs/PROGRESS.md` (milestones) |
| Figures/tables | Roadmap table (M8 rebrand, M9 assets, M10 deploy, optional Phase 11) |
| You must write | Conclusions against your original objectives, contributions, and future work: Neon deployment, calendar sync, teams, payments (D-08), abuse detection (Phase 11, advisory only) |

---

## Appendices (recommended)

| Appendix | Source |
| --- | --- |
| A. Requirement register | `docs/PARITY.md` §1 |
| B. Full traceability matrix | `docs/TRACEABILITY.md` §1–§2 |
| C. API reference | `docs/00_ANALYSIS.md` §4 + route list in `docs/TRACEABILITY.md` |
| D. Database schema and migrations | `apps/api/prisma/schema.prisma`, `apps/api/prisma/migrations/` |
| E. Test inventory and commands | `docs/TEST_REPORT.md` §4–§7, §15 |
| F. Decisions and deviations | `docs/DECISIONS.md` |
| G. Performance artefacts | `docs/perf/*.json` (list the files, summarise, do not paste JSON) |
| H. Accessibility artefacts | `docs/a11y/*.json` + the contrast summary table |
| I. Setup guide | `README.md` + `docs/README_CHECK.md` |

## Figures you still have to produce by hand

These exist as data or code, not as images:

1. **ER diagram** — 7 tables from `schema.prisma` (draw it; include the EXCLUDE
   constraint on `bookings`).
2. **Architecture diagram** — browser SPA, Express API, PostgreSQL, outbox
   worker, email provider; mark the trust boundaries (session cookie, CSRF,
   bearer management token).
3. **Booking sequence diagram** — the transaction order above.
4. **Screen map** — S01–S11 with the two flows (owner setup, invitee booking).
5. **Screenshots** — 390 px and 1440 px of S01, S02, S03, S06, S07, S09, S10
   (the a11y suite already drives these screens; capture while running it).
6. **Chart: NFR-01 before/after** — one bar pair per endpoint from §9.2/§9.4.

## Suggested chapter length (adjust to your regulations)

Intro 8 %, literature 15 %, requirements 12 %, design 18 %, implementation 17 %,
testing 15 %, results 8 %, limitations 4 %, conclusion 3 %. The repo is heaviest
on design/testing/implementation; the literature review is the chapter that needs
the most new work.
