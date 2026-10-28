# README_CHECK.md — clean-clone setup test (M7, task 5)

Question: can a new developer get Slotwise running by following `README.md`
alone, in under 10 minutes?

Method: cloned the repository into an empty temp folder
(`%TEMP%\slotwise-clean\slotwise`), followed the README steps in order with a
stopwatch, and used a **fresh database** (`slotwise_readme`) so nothing was
pre-warmed. Every step was executed for real; nothing was assumed to work.

## 1. What happened (first attempt, original README)

| Step | Time | Result |
| --- | --- | --- |
| `git clone` | 2.4 s | OK |
| `cp .env.example .env` + fill values | 0.4 s | OK (root `.env` only, as the README said) |
| `pnpm install --frozen-lockfile` | **243.9 s** | OK (cold store, slow registry: 49 KiB/s) |
| `docker compose up -d` | — | **Skipped**: Docker is not installed on this machine (A-08); used the native PostgreSQL 18.3 instead |
| `CREATE EXTENSION pgcrypto, btree_gist` | 1.5 s | OK |
| `pnpm db:migrate` | 5.9 s | **FAILED** |
| `pnpm db:migrate` again, after copying the same `.env` to `apps/api/.env` | 18.9 s | OK — `20261027085107_init` applied, "database is now in sync" |
| `pnpm dev` | ~10 s to listen | OK: api on :4000, web on :5173 |

**Time to a working database: 4 min 33 s** (2.4 s + 243.9 s + 1.5 s + 18.9 s
+ copy). Under the 10-minute target with room to spare — but only after an
undocumented workaround.

### The failure

```
$ pnpm db:migrate
error: Environment variable not found: DATABASE_URL.
```

Cause: the API and the Prisma CLI load dotenv relative to **their own working
directory** (`apps/api`), so the root `.env` created by the README is never read.
The README's step 1 was therefore correct-looking and wrong in practice.

Second failure mode, same root cause: `pnpm dev` starts the API in `apps/api`,
which would also have started without a database URL and failed on first query.
It did not fail here only because the workaround had already created
`apps/api/.env`.

### What else was missing or wrong in the original README

| # | Problem | Consequence |
| --- | --- | --- |
| 1 | Only the root `.env` was documented | `pnpm db:migrate` and the API cannot see `DATABASE_URL` |
| 2 | `Node.js >= 20` | CI and this machine run Node 22 (`engines.node >= 22` since DEV-22) |
| 3 | No database creation step | `createdb`/`docker compose` were implied, not stated |
| 4 | No test instructions at all | A new developer could not reproduce a single result in `docs/TEST_REPORT.md` |
| 5 | No seed instructions | E2E/`seed:e2e` and the perf fixture were undiscoverable |
| 6 | `verify:neon`, `perf`, `delete:account` scripts undocumented | Half the `package.json` scripts were unexplained |
| 7 | Status said "Phase 0" and `docs/TRACEABILITY.md` was listed as "to be produced" | Both stale (TRACEABILITY exists as of this milestone) |
| 8 | No ports listed | `pnpm dev` prints them, but the README did not say which to open |
| 9 | No `pnpm exec playwright install chromium` | `pnpm test:e2e` fails on a machine without browsers |

## 2. Fix applied

`README.md` was rewritten in this milestone:

- both env files (`.env` **and** `apps/api/.env`) with the reason, and the
  requirement that the two `DATABASE_URL` values match;
- Node `>= 22`;
- explicit database creation, extension and migration steps
  (`db:migrate:deploy` vs `db:migrate`);
- ports and health endpoints;
- optional seed commands (`seed:e2e`, `seed:perf`);
- a test section with the real counts and the caveats (CSRF bypass, raised rate
  limits, Playwright browser install);
- a docs index and the known-limitations pointer to `docs/GAPS.md`.

## 3. Second attempt (verification of the fix)

The corrected README was verified against the same clean-clone layout, using the
already-installed `node_modules` (a second cold install would only re-measure
registry bandwidth, not the README):

- `apps/api/.env` created as documented → `pnpm db:migrate` succeeds first time;
- `pnpm dev` → `GET http://localhost:4000/health` → **200**
  `{"status":"ok","service":"slotwise-api","version":"0.0.0"}`;
- `GET http://localhost:4000/health/ready` → **200** (database reachable);
- `GET http://127.0.0.1:5173/` → **200**, 670 bytes of SPA shell;
- `GET /api/v1/public/intro-tutoring` → **404** — correct: a fresh database has
  no seed data, and the README now says how to create some.

Scratch database `slotwise_readme` and the temp clone were removed afterwards.

## 4. Honest limits of this check

- One machine (Windows 11, Node 22.16, pnpm 12.15, PostgreSQL 18.3), one network.
  Install time is dominated by registry bandwidth and would differ elsewhere.
- The second pass reused the installed `node_modules`, so it verifies the
  *instructions*, not a second cold install.
- Docker was unavailable, so the `docker compose` path was **not** exercised;
  the native-PostgreSQL path was.
- No new developer was observed — this is a scripted reproduction, not a
  usability study of the README (that would be G-07's task-test cousin).
