import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/concurrency/**/*.test.ts"],
    testTimeout: 60000,
  },
});