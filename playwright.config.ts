import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end suite: real web app -> real Express API -> real PostgreSQL.
 * The database is seeded by tests/e2e/global-setup.ts before anything runs.
 * Browsers run headless (full Chromium in new-headless mode).
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  globalSetup: "./tests/e2e/global-setup.ts",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
    headless: true,
  },
  projects: [
    {
      name: "setup",
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: "chromium",
      testMatch: /.*\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        headless: true,
        // Pin the invitee time zone so zone-specific assertions are stable.
        timezoneId: "America/New_York",
        storageState: "tests/e2e/.auth/owner.json",
      },
      dependencies: ["setup"],
    },
  ],
  // Two separate servers instead of `pnpm dev`: pnpm's `--parallel` output
  // multiplexer stalls when its stdout is a pipe (as it is under Playwright),
  // so the dev stack would never become ready.
  webServer: [
    {
      command: "pnpm --filter @slotwise/web dev",
      url: "http://localhost:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
    {
      command: "pnpm --filter @slotwise/api dev",
      url: "http://localhost:4000/health",
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      // The E2E run makes far more requests than a human would. Raise the abuse
      // limits for the test server only; the real limits are proven by the API
      // security suite (tests/security), which expects 429s.
      env: {
        RATE_LIMIT_LOGIN_MAX: "500",
        RATE_LIMIT_REGISTER_MAX: "500",
        RATE_LIMIT_SLOTS_MAX: "5000",
        RATE_LIMIT_BOOKING_MAX: "500",
      },
    },
  ],
});
