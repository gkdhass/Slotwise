/**
 * Produces the runtime bundle for the API: dist/server.js.
 *
 * Why a bundle at all: `@slotwise/shared` (the slot generator) is published as
 * TypeScript source so that Vite, tsx and vitest can consume it directly with no
 * build step. Plain `node` cannot load a .ts file, so `node dist/index.js`
 * crashed with ERR_UNKNOWN_FILE_EXTENSION. Bundling inlines the workspace
 * packages while leaving real npm dependencies external (resolved from
 * node_modules at runtime, exactly as npm would install them).
 *
 * `tsc -b` still runs first: it type-checks and emits declarations/source maps
 * used for debugging.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));

// Keep every npm dependency external, but bundle workspace source packages.
// `resend` is not installed by default: src/lib/email.ts imports it lazily and
// falls back to console delivery when the package or API key is absent, so it
// must stay external rather than being bundled (or failed on).
const external = [
  ...Object.keys(pkg.dependencies ?? {}).filter((name) => !name.startsWith("@slotwise/")),
  "resend",
];

await build({
  entryPoints: [fileURLToPath(new URL("../src/index.ts", import.meta.url))],
  outfile: fileURLToPath(new URL("../dist/server.js", import.meta.url)),
  bundle: true,
  platform: "node",
  format: "esm",
  target: "node20",
  sourcemap: true,
  external,
  logLevel: "info",
});
