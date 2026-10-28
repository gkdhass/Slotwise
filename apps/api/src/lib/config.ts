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
