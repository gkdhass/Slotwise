import { Request, Response, NextFunction } from "express";

type Bucket = { count: number; resetAt: number };

const buckets = new Map<string, Bucket>();

/** Test helper: clear all counters. */
export function resetRateLimits(): void {
  buckets.clear();
}

function num(name: string, fallback: number): number {
  const v = Number(process.env[name]);
  return Number.isFinite(v) && v > 0 ? v : fallback;
}

export interface RateLimitOptions {
  /** Logical name, used for the env overrides and the bucket key. */
  name: string;
  /** Window length in ms. */
  windowMs: number;
  /** Max requests per window. */
  max: number;
  /** Extra key material (for example the submitted email on login). */
  key?: (req: Request) => string;
}

/**
 * Fixed-window in-memory limiter. Returns 429 with the standard error
 * envelope plus a Retry-After header once the window is exhausted.
 */
export function rateLimit(opts: RateLimitOptions) {
  const envMax = `${"RATE_LIMIT_"}${opts.name.toUpperCase()}_MAX`;
  const envWindow = `${"RATE_LIMIT_"}${opts.name.toUpperCase()}_WINDOW_MS`;

  return function limiter(req: Request, res: Response, next: NextFunction) {
    const max = num(envMax, opts.max);
    const windowMs = num(envWindow, opts.windowMs);
    const extra = opts.key?.(req) ?? "";
    const key = `${opts.name}:${req.ip}:${extra}`;
    const now = Date.now();
    let b = buckets.get(key);
    if (!b || b.resetAt <= now) {
      b = { count: 0, resetAt: now + windowMs };
      buckets.set(key, b);
    }
    b.count += 1;
    const remaining = Math.max(0, max - b.count);
    res.setHeader("X-RateLimit-Limit", String(max));
    res.setHeader("X-RateLimit-Remaining", String(remaining));
    if (b.count > max) {
      const retryAfter = Math.ceil((b.resetAt - now) / 1000);
      res.setHeader("Retry-After", String(retryAfter));
      return res.status(429).json({
        error: {
          code: "RATE_LIMITED",
          message: "Too many requests. Try again later.",
          requestId: (req as Request & { id?: string }).id ?? "",
          fieldErrors: {},
        },
      });
    }
    next();
  };
}
