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
  if (trustProxyHops(env) === null) {
    problems.push(
      "TRUST_PROXY must be the exact number of proxy hops in front of the API " +
        "(for example TRUST_PROXY=1 on Render/Railway); " +
        '"true", "false", "loopback" and unset are refused in production because ' +
        "they would let a client choose its own req.ip via X-Forwarded-For",
    );
  }
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
 * `TRUST_PROXY` is the number of reverse-proxy hops in front of this process.
 * With `TRUST_PROXY=1` Express takes the **rightmost** `X-Forwarded-For` entry
 * (the address the single proxy saw, i.e. the one the proxy appended) and
 * ignores everything to its left, so a client cannot forge it. With
 * `TRUST_PROXY=false` the header is ignored entirely and `req.ip` is the socket
 * address. Default is `false` (correct for local dev, tests and any host that
 * exposes the port directly).
 *
 * Production requires an exact positive integer: see `assertProductionSafety`.
 * Non-production also accepts the other forms Express understands (`loopback`,
 * a subnet, even `true`) so a developer can experiment, but those are refused
 * at startup in production.
 */
export function trustProxySetting(env: NodeJS.ProcessEnv = process.env): boolean | number | string {
  const raw = (env.TRUST_PROXY ?? "").trim();
  if (raw === "" || raw === "false" || raw === "0") return false;
  const hops = trustProxyHops(env);
  if (hops !== null) return hops;
  return raw;
}

/**
 * The configured hop count, or `null` when `TRUST_PROXY` is not an exact
 * positive integer. Used by the production guard so the accepted production
 * configuration is the same value used to boot Express.
 */
export function trustProxyHops(env: NodeJS.ProcessEnv = process.env): number | null {
  const raw = (env.TRUST_PROXY ?? "").trim();
  if (!/^[1-9]\d*$/.test(raw)) return null;
  const n = Number(raw);
  return Number.isSafeInteger(n) ? n : null;
}
