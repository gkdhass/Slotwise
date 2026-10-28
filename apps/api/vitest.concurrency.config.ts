import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/concurrency/**/*.test.ts"],
    setupFiles: ["./tests/setup.ts"],
    testTimeout: 120000,
    hookTimeout: 60000,
    env: {
      CSRF_DISABLED: "true",
      RATE_LIMIT_BOOKING_MAX: "100000",
      RATE_LIMIT_SLOTS_MAX: "100000",
      RATE_LIMIT_LOGIN_MAX: "100000",
      RATE_LIMIT_REGISTER_MAX: "100000",
    },
    fileParallelism: false,
  },
});
