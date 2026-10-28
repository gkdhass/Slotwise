/**
 * Startup safety checks and configuration.
 *
 * Rule: the CSRF bypass may only ever be active when NODE_ENV === "test".
 * A production process that is asked to bypass CSRF fails fast at startup
 * instead of silently running unprotected.
 */

export function csrfBypassActive(env: NodeJS.ProcessEnv = process.env): boolean {
  return env.NODE_ENV === "test" && env.CSRF_DISABLED === "true";
}

export function assertProductionSafety(env: NodeJS.ProcessEnv = process.env): void {
  if (env.NODE_ENV !== "production") return;
  const problems: string[] = [];
  if (env.CSRF_DISABLED === "true") {
    problems.push("CSRF_DISABLED=true is not allowed when NODE_ENV=production");
  }
  if (!env.SESSION_SECRET || env.SESSION_SECRET.length < 16) {
    problems.push("SESSION_SECRET must be set to at least 16 characters in production");
  }
  if (!env.DATABASE_URL) problems.push("DATABASE_URL is required");
  if (problems.length > 0) {
    throw new Error(`Refusing to start: ${problems.join("; ")}`);
  }
}

export function corsAllowList(env: NodeJS.ProcessEnv = process.env): string[] {
  const raw = env.CORS_ALLOWED_ORIGINS ?? env.APP_BASE_URL ?? "http://localhost:5173";
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * Express's `trust proxy` setting.
 *
 * It used to be `1` unconditionally, which means `req.ip` came from
 * `X-Forwarded-For` even when nothing in front of the process was stripping it:
 * any client that could reach the port directly could rotate that header and
 * reset every per-IP rate-limit counter. The setting is now explicit.
 *
 * `TRUST_PROXY` accepts what Express accepts (`1`, `2`, `loopback`, a subnet, or
 * `true`), and defaults to `false` (use the socket address). A platform behind a
 * proxy — Render, Railway, Vercel — must set `TRUST_PROXY=1`.
 */
export function trustProxySetting(env: NodeJS.ProcessEnv = process.env): boolean | number | string {
  const raw = (env.TRUST_PROXY ?? "").trim();
  if (raw === "" || raw === "false" || raw === "0") return false;
  if (raw === "true") return true;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : raw;
}
