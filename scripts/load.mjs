/**
 * NFR-01 load check: "read API p95 < 500 ms" (docs/00_ANALYSIS.md).
 *
 *   pnpm perf                       full run (build + seed + start + measure)
 *   pnpm perf --skip-build          reuse the current dist/server.js
 *   pnpm perf --connections 50 --duration 30
 *   pnpm perf --autocannon          add an independent autocannon cross-check
 *
 * Steps, with no manual setup:
 *   1. build the API (compiled bundle, not `tsx watch`)
 *   2. seed a dedicated published event (`perf-load-test`)
 *   3. start the built server on port 4100 with NODE_ENV=production
 *   4. warm up, then measure GET /api/v1/public/:slug and its /slots
 *   5. assert p95 <= 500 ms with zero errors / zero non-2xx
 *   6. print a table and write docs/perf/<timestamp>.json
 *
 * Load profile: 20 concurrent connections, closed loop (a connection sends the
 * next request as soon as the previous response completes), no think time, 20 s
 * per endpoint after a discarded 5 s warm-up.
 *
 * Why the latency numbers are computed here instead of taken from autocannon:
 * autocannon's histogram reports p50/p75/p90/p97_5/p99 but never p95, so it
 * cannot answer an NFR written as p95. This harness records the wall-clock
 * latency of every single request and computes the percentiles exactly.
 * `--autocannon` runs the standard tool as well, for an rps/p97_5 cross-check.
 *
 * Rate limiting is raised for the measurement only: the limiter is a separate
 * concern (the security suite proves its 429 behaviour) and would otherwise cap
 * the run at 120 requests/minute and measure nothing.
 */
import autocannon from "autocannon";
import { execFileSync, spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";

const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  if (i === -1) return fallback;
  const value = Number(args[i + 1]);
  return Number.isFinite(value) ? value : fallback;
};
const has = (name) => args.includes(`--${name}`);

const CONNECTIONS = flag("connections", 20);
const DURATION = flag("duration", 20);
const WARMUP = flag("warmup", 5);
const PORT = flag("port", 4100);
const BASE = `http://127.0.0.1:${PORT}`;
const SLUG = "perf-load-test";
const NFR_01_P95_MS = 500;

const root = process.cwd();
const apiDir = path.join(root, "apps", "api");

function run(cmd, cmdArgs) {
  execFileSync(cmd, cmdArgs, {
    cwd: root,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
}

function dbInfo() {
  const code = `
    import("dotenv/config").catch(() => {});
    const { PrismaClient } = await import("@prisma/client");
    const prisma = new PrismaClient();
    try {
      const rows = await prisma.$queryRawUnsafe("select version() as v, current_database() as db");
      console.log(JSON.stringify({ version: rows[0].v, database: rows[0].db }));
    } finally {
      await prisma.$disconnect();
    }
  `;
  try {
    const out = execFileSync(process.execPath, ["--input-type=module", "-e", code], {
      cwd: apiDir,
      env: process.env,
      encoding: "utf8",
    });
    return JSON.parse(out.trim().split(/\r?\n/).pop());
  } catch {
    return { version: "unknown", database: "unknown" };
  }
}

function dbTarget() {
  try {
    const out = execFileSync(process.execPath, ["scripts/check-db-target.mjs"], {
      cwd: root,
      env: process.env,
      encoding: "utf8",
    });
    const line = out.split(/\r?\n/).find((l) => l.includes("host-type="));
    return line ? line.trim().replace(/^\.env: /, "") : "unknown";
  } catch {
    return "unknown";
  }
}

async function waitForHealth(timeoutMs = 60_000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const res = await fetch(`${BASE}/health`);
      if (res.ok) return true;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  return false;
}

function slotsUrl() {
  const from = new Date(Date.now() + 1 * 86_400_000);
  const to = new Date(from.getTime() + 7 * 86_400_000);
  const qs = new URLSearchParams({ from: from.toISOString(), to: to.toISOString(), tz: "Asia/Kolkata" });
  return `${BASE}/api/v1/public/${SLUG}/slots?${qs.toString()}`;
}

/** Exact percentile over sorted samples, using the nearest-rank method. */
function percentile(sorted, p) {
  if (sorted.length === 0) return 0;
  const rank = Math.ceil((p / 100) * sorted.length) - 1;
  return sorted[Math.min(Math.max(rank, 0), sorted.length - 1)];
}

/**
 * Closed-loop load for `durationMs` with `connections` concurrent keep-alive
 * sockets. Every request's latency is recorded so p95 is exact.
 */
function generateLoad(urlString, { connections, durationMs }) {
  const url = new URL(urlString);
  const agent = new http.Agent({ keepAlive: true, maxSockets: connections });
  const latencies = [];
  let errors = 0;
  let non2xx = 0;
  const deadline = Date.now() + durationMs;

  const one = () =>
    new Promise((resolve) => {
      const started = process.hrtime.bigint();
      const req = http.request(
        {
          protocol: url.protocol,
          hostname: url.hostname,
          port: url.port,
          path: `${url.pathname}${url.search}`,
          method: "GET",
          agent,
          headers: { accept: "application/json", connection: "keep-alive" },
        },
        (res) => {
          res.resume();
          res.on("end", () => {
            const ms = Number(process.hrtime.bigint() - started) / 1e6;
            if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
              latencies.push(ms);
            } else {
              non2xx += 1;
            }
            resolve();
          });
        },
      );
      req.on("error", () => {
        errors += 1;
        resolve();
      });
      req.end();
    });

  const worker = async () => {
    while (Date.now() < deadline) await one();
  };

  const startedAt = Date.now();
  return Promise.all(Array.from({ length: connections }, worker)).then(() => {
    agent.destroy();
    const seconds = (Date.now() - startedAt) / 1000;
    const sorted = latencies.slice().sort((a, b) => a - b);
    const total = sorted.length + non2xx + errors;
    return {
      requests: total,
      ok: sorted.length,
      rps: Number((total / seconds).toFixed(1)),
      p50: Number(percentile(sorted, 50).toFixed(1)),
      p95: Number(percentile(sorted, 95).toFixed(1)),
      p99: Number(percentile(sorted, 99).toFixed(1)),
      max: Number((sorted[sorted.length - 1] ?? 0).toFixed(1)),
      mean: Number((sorted.reduce((a, b) => a + b, 0) / (sorted.length || 1)).toFixed(1)),
      non2xx,
      errors,
    };
  });
}

async function measure(url) {
  await generateLoad(url, { connections: CONNECTIONS, durationMs: WARMUP * 1000 }); // discarded warm-up
  return generateLoad(url, { connections: CONNECTIONS, durationMs: DURATION * 1000 });
}

async function crossCheck(url) {
  const result = await autocannon({
    url,
    connections: CONNECTIONS,
    duration: DURATION,
    headers: { accept: "application/json" },
  });
  return {
    requests: result.requests.total,
    rps: Number(result.requests.average.toFixed(1)),
    p50: result.latency.p50,
    p95NotReported: "autocannon emits p97_5, not p95",
    p97_5: result.latency.p97_5,
    p99: result.latency.p99,
    max: result.latency.max,
    non2xx: result.non2xx,
    errors: result.errors,
  };
}

async function main() {
  const meta = {
    startedAt: new Date().toISOString(),
    node: process.version,
    platform: `${os.type()} ${os.release()} (${process.platform} ${os.arch()})`,
    cpu: (os.cpus()[0]?.model ?? "unknown").trim(),
    cores: os.cpus().length,
    memoryGb: Number((os.totalmem() / 1024 ** 3).toFixed(1)),
    apiMode: "compiled bundle (node dist/server.js), NODE_ENV=production",
    loadGenerator: "node:http closed loop, per-request latency sampling (exact p95)",
    profile: { connections: CONNECTIONS, durationSeconds: DURATION, warmupSeconds: WARMUP, thinkTime: "none" },
    rateLimits: "raised for the measurement (RATE_LIMIT_*_MAX=1000000)",
    ...dbInfo(),
    dbTarget: dbTarget(),
  };

  console.log("\n== environment ==");
  for (const [k, v] of Object.entries(meta)) {
    console.log(`   ${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`);
  }

  if (!has("skip-build")) {
    console.log("\n== building api ==");
    run("pnpm", ["--filter", "@slotwise/api", "build"]);
  }

  console.log("\n== seeding perf fixture ==");
  run("pnpm", ["--filter", "@slotwise/api", "seed:perf"]);

  const env = {
    ...process.env,
    NODE_ENV: "production",
    PORT: String(PORT),
    SESSION_SECRET: "load-test-only-session-secret-not-a-real-deployment",
    RATE_LIMIT_SLOTS_MAX: "1000000",
    RATE_LIMIT_BOOKING_MAX: "1000000",
    RATE_LIMIT_LOGIN_MAX: "1000000",
    RATE_LIMIT_REGISTER_MAX: "1000000",
  };
  console.log(`\n== starting api on ${BASE} ==`);
  const server = spawn(process.execPath, ["dist/server.js"], {
    cwd: apiDir,
    env,
    stdio: "ignore", // keep log piping out of the measurement
  });

  const shutdown = () => {
    try {
      server.kill();
    } catch {
      /* already gone */
    }
  };
  process.on("exit", shutdown);
  process.on("SIGINT", () => {
    shutdown();
    process.exit(130);
  });

  if (!(await waitForHealth())) {
    shutdown();
    throw new Error(`api did not become healthy on ${BASE}`);
  }

  const slugUrl = `${BASE}/api/v1/public/${SLUG}`;
  const slots = slotsUrl();
  for (const url of [slugUrl, slots]) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${url} -> ${res.status}`);
    if (url === slots) {
      const body = await res.json();
      if (!Array.isArray(body) || body.length === 0) throw new Error("slots endpoint returned no slots");
      const kib = Math.round((JSON.stringify(body).length / 1024) * 10) / 10;
      console.log(`\n== slots window: ${body.length} slots, ${kib} KiB response ==`);
    }
  }

  console.log(`\n== measuring GET /api/v1/public/${SLUG} ==`);
  const slugResult = await measure(slugUrl);
  console.log(`\n== measuring GET /api/v1/public/${SLUG}/slots ==`);
  const slotsResult = await measure(slots);

  let cross = null;
  if (has("autocannon")) {
    console.log("\n== autocannon cross-check (standard tool, p97_5 not p95) ==");
    cross = {
      slug: await crossCheck(slugUrl),
      slots: await crossCheck(slots),
    };
  }

  shutdown();

  const checks = [
    { name: "GET /public/:slug", ...slugResult },
    { name: "GET /public/:slug/slots", ...slotsResult },
  ];

  console.log("\n== results (NFR-01: p95 < 500 ms) ==");
  console.log("endpoint                            rps     p50     p95     p99     max    non2xx  errors");
  for (const c of checks) {
    console.log(
      `${c.name.padEnd(32)}${String(c.rps).padStart(8)}${String(c.p50).padStart(8)}${String(c.p95).padStart(8)}` +
        `${String(c.p99).padStart(8)}${String(c.max).padStart(8)}${String(c.non2xx).padStart(8)}${String(c.errors).padStart(8)}`,
    );
  }
  if (cross) {
    console.log("\n== autocannon cross-check ==");
    console.log("endpoint                            rps     p50   p97_5     p99     max    non2xx  errors");
    for (const [name, c] of [
      ["GET /public/:slug", cross.slug],
      ["GET /public/:slug/slots", cross.slots],
    ]) {
      console.log(
        `${name.padEnd(32)}${String(c.rps).padStart(8)}${String(c.p50).padStart(8)}${String(c.p97_5).padStart(8)}` +
          `${String(c.p99).padStart(8)}${String(c.max).padStart(8)}${String(c.non2xx).padStart(8)}${String(c.errors).padStart(8)}`,
      );
    }
  }

  const failures = [];
  for (const c of checks) {
    if (c.p95 > NFR_01_P95_MS) failures.push(`${c.name}: p95 ${c.p95} ms exceeds ${NFR_01_P95_MS} ms`);
    if (c.non2xx > 0) failures.push(`${c.name}: ${c.non2xx} non-2xx responses`);
    if (c.errors > 0) failures.push(`${c.name}: ${c.errors} connection errors`);
  }

  const artifact = { meta, checks, crossCheck: cross, nfr01: { metric: "p95", limitMs: NFR_01_P95_MS, pass: failures.length === 0 } };
  const dir = path.join(root, "docs", "perf");
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, `load-${new Date().toISOString().replace(/[:.]/g, "-")}.json`);
  fs.writeFileSync(file, `${JSON.stringify(artifact, null, 2)}\n`);
  console.log(`\nartifact: ${path.relative(root, file)}`);

  if (failures.length > 0) {
    console.log("\nRESULT: FAIL");
    for (const f of failures) console.log(`  - ${f}`);
    process.exit(1);
  }
  console.log(`\nRESULT: PASS — both endpoints p95 < ${NFR_01_P95_MS} ms, no errors`);
}

main().catch((err) => {
  console.error(`\nRESULT: ERROR — ${err.message}`);
  process.exit(1);
});
