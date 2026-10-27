# Slotwise

Focused single-host scheduling MVP (final-year project). Clean-room implementation; not affiliated with any third-party scheduling product.

## Status
Phase 0 — analysis & setup. See `docs/PROGRESS.md`.

## Stack
- Frontend: React + Vite + Tailwind CSS (`apps/web`)
- Backend: Node.js + Express, TypeScript (`apps/api`)
- Database: PostgreSQL (Prisma) — D-01 pending confirmation
- Workspaces: pnpm

## Prerequisites
- Node.js >= 20
- pnpm 12.x (`npm i -g pnpm`)
- PostgreSQL 16 (Docker optional: `docker compose up -d`)

## Setup (target < 10 min)
1. `cp .env.example .env` and fill values.
2. `pnpm install`
3. `docker compose up -d` (or point `DATABASE_URL` at a Postgres instance)
4. `pnpm db:migrate`
5. `pnpm dev`

## Scripts
- `pnpm dev` — run web + api
- `pnpm build` — build all
- `pnpm lint` / `pnpm typecheck` / `pnpm test`
- `pnpm test:e2e` — Playwright
- `pnpm worker:email` — run outbox worker

## Docs
- `docs/00_ANALYSIS.md`, `docs/DECISIONS.md`, `docs/PROGRESS.md`
- Source PDFs: `docs/source/`
- `docs/TRACEABILITY.md`, `docs/TEST_REPORT.md`, `docs/PRIVACY.md`, `docs/DEPLOYMENT.md` (to be produced in later phases)

## License
TBD (project). No third-party code copied.