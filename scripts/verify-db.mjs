import { spawnSync } from "node:child_process";

/**
 * Full database verification against whatever DATABASE_URL is configured.
 *
 *   pnpm verify:neon
 *
 * Runs, in order:
 *   1. target check            (host type only — never the connection string)
 *   2. prisma migrate deploy
 *   3. exclusion-constraint + 23P01 probe   (Prisma only, no psql)
 *   4. integration suite
 *   5. security suite
 *   6. concurrency suite
 *
 * Points at Neon simply by putting the Neon direct URL in .env; nothing here is
 * Neon-specific. Any failure aborts with a non-zero exit code.
 */

const steps = [
  { name: "database target", cmd: "node", args: ["scripts/check-db-target.mjs"] },
  {
    name: "prisma migrate deploy",
    cmd: "pnpm",
    args: ["--filter", "@slotwise/api", "exec", "prisma", "migrate", "deploy"],
  },
  { name: "constraint + 23P01 probe", cmd: "pnpm", args: ["--filter", "@slotwise/api", "verify:constraint"] },
  { name: "integration suite", cmd: "pnpm", args: ["--filter", "@slotwise/api", "test:integration"] },
  { name: "security suite", cmd: "pnpm", args: ["--filter", "@slotwise/api", "test:security"] },
  { name: "concurrency suite", cmd: "pnpm", args: ["--filter", "@slotwise/api", "test:concurrency"] },
];

const results = [];
const started = Date.now();

for (const [index, step] of steps.entries()) {
  console.log(`\n${"=".repeat(70)}`);
  console.log(`[${index + 1}/${steps.length}] ${step.name}`);
  console.log("=".repeat(70));
  const t0 = Date.now();
  const res = spawnSync(step.cmd, step.args, {
    stdio: "inherit",
    shell: process.platform === "win32",
    env: process.env,
  });
  const ms = Date.now() - t0;
  const ok = res.status === 0;
  results.push({ name: step.name, ok, ms });
  if (!ok) {
    console.log(`\nFAILED at step ${index + 1}: ${step.name} (exit ${res.status})`);
    break;
  }
}

console.log(`\n${"=".repeat(70)}`);
console.log("SUMMARY");
console.log("=".repeat(70));
for (const r of results) {
  console.log(`${r.ok ? "PASS" : "FAIL"}  ${r.name.padEnd(28)} ${(r.ms / 1000).toFixed(1)}s`);
}
const failed = results.filter((r) => !r.ok);
const allOk = failed.length === 0 && results.length === steps.length;
console.log(`\n${allOk ? "RESULT: PASS" : "RESULT: FAIL"} — ${results.length}/${steps.length} steps, ${((Date.now() - started) / 1000).toFixed(1)}s total`);
process.exit(allOk ? 0 : 1);
