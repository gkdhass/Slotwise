import { defineConfig } from "vitest/config";

// Security suite: CSRF is ENFORCED (no CSRF_DISABLED), rate limits are
// exercised with small windows, and the production startup guard is checked.
export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/security/**/*.test.ts"],
    setupFiles: ["./tests/setup.ts"],
    hookTimeout: 60000,
    testTimeout: 60000,
    env: {
      CSRF_DISABLED: "false",
    },
    fileParallelism: false,
  },
});
