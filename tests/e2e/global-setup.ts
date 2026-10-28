import { execSync } from "node:child_process";

/**
 * Deterministic fixture for the whole E2E run: one verified owner with two
 * published event types and no bookings. Runs once, before any project.
 */
export default function globalSetup() {
  execSync("pnpm --filter @slotwise/api seed:e2e", {
    cwd: process.cwd(),
    stdio: "inherit",
    env: process.env,
  });
}
