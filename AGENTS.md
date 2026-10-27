# AGENTS.md — Slotwise

This file persists operating rules for any agent working in this repo. Full master prompt lives in the project's first-message context; this is the condensed, repo-local version.

## Project identity
Slotwise — focused single-host scheduling MVP (final-year project). Clean-room; do not copy Calendly code/copy/logos/fonts/icons/palette. Stack: React+Vite+Tailwind (web), Node+Express (api), TypeScript, Prisma + PostgreSQL, pnpm workspaces.

## Read first
- `docs/00_ANALYSIS.md`, `docs/DECISIONS.md`, `docs/PROGRESS.md`.
- Source PDFs in `docs/source/`.
- Priority order on conflicts: Decisions → PRD → TRD → Backend Schema → Application Flow → UI/UX → Implementation Plan → IEEE paper.

## Operating rules
1. Read before write. Never code before `docs/00_ANALYSIS.md` exists (it does).
2. Source of truth priority above. Record conflicts in `docs/DECISIONS.md` (ID, conflict, resolution, date).
3. Never invent facts. Label unmeasured as "target"/"hypothesis"; synthetic data always labelled synthetic.
4. Clean-room: original design tokens only (see docs/UI? tokens in master prompt §9). No Calendly assets.
5. Small verified steps: lint + typecheck + relevant tests after each task. Conventional Commits, one logical change per commit, feature branch per milestone (`m0-shell`, `m1-slice`, …).
6. Ask only when blocked by a genuinely owner decision (credentials, naming, legal/privacy). Otherwise state assumption in DECISIONS.md and continue.
7. Security hygiene: no secrets in code/git; `.env.example` names only; never log passwords/tokens/PII.
8. Maintain `docs/PROGRESS.md` (milestone, task IDs, test status, risks).
9. Report format at every gate: What was built · What was tested (commands+results) · Deviations · Risks/open questions · What I need from you.
10. Stop at every GATE and wait for approval.

## Key decisions (see docs/DECISIONS.md)
- D-01 PostgreSQL (pending Gate 0 confirmation). D-02 Prisma. D-03 TypeScript. D-04 React/Vite/Tailwind + Express + Zod. D-05 server sessions/Argon2id/CSRF. D-06 Resend + outbox. D-07 Vercel (pending Gate 0). D-08 payments deferred. D-09 pricing ₹ hypothesis, not implemented. D-10 IEEE paper → optional advisory Phase 11 only.

## Critical invariant (never disable)
`bookings_no_host_overlap` EXCLUDE constraint (GiST). Booking transaction order per master prompt §7. Outbox: poll `FOR UPDATE SKIP LOCKED`, send only after commit.

## Gates
Phase 0 → GATE 0 (confirm D-01, D-07). M1 → GATE 1. M4 → GATE 2. M6 → GATE 3. M10 → GATE 4. Phase 11 only after Gate 3 + owner says "start Phase 11".