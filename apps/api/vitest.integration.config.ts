import { defineConfig } from "vitest/config";

// Integration suite runs the real Express app against the real database
// (DATABASE_URL from .env). CSRF is bypassed here only, via CSRF_DISABLED;
// the dedicated security suite runs with CSRF enforced.
export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/integration/**/*.test.ts"],
    setupFiles: ["./tests/setup.ts"],
    hookTimeout: 60000,
    testTimeout: 60000,
    env: {
      CSRF_DISABLED: "true",
      RATE_LIMIT_BOOKING_MAX: "1000",
      RATE_LIMIT_SLOTS_MAX: "1000",
      RATE_LIMIT_LOGIN_MAX: "1000",
      RATE_LIMIT_REGISTER_MAX: "1000",
    },
    fileParallelism: false,
  },
});
