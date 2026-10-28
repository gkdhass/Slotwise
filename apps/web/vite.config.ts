import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Bind IPv4 loopback explicitly. Vite's default resolves `localhost` to
    // `::1` on Windows, which makes `http://127.0.0.1:5173` refuse connections —
    // that is the address Playwright's web-server readiness probe uses.
    host: "127.0.0.1",
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});