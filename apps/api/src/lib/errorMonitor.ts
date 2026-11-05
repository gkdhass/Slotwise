import { logger } from "./logger.js";

/**
 * Error monitoring hook (NFR-05).
 *
 * Unhandled server errors are reported in two ways:
 *   1. always as a structured `error` log line carrying the request id, method
 *      and redacted path — so an operator can go from a user's quoted request id
 *      to the failure;
 *   2. if `ERROR_MONITOR_WEBHOOK_URL` is set, as a JSON POST to that endpoint
 *      (an error tracker, a Slack webhook, anything that accepts JSON).
 *
 * Deliberate constraints:
 *   - Reporting never throws and never delays the response: it is fire-and-forget
 *     with a short timeout, because a broken monitor must not break the API.
 *   - No request body, cookie, header or query string is ever sent. Management
 *     tokens live in the URL path, so long token-like path segments are masked.
 */

const WEBHOOK_TIMEOUT_MS = 2_000;

export type ErrorReport = {
  requestId: string;
  method: string;
  path: string;
  status: number;
  name: string;
  message: string;
  stack?: string;
};

/**
 * Masks bearer-token path segments. Management links are `/manage/<64 hex>` and
 * `/api/v1/manage/<64 hex>/cancel`, so anything long and opaque is redacted
 * while normal slugs (`intro-tutoring`) stay readable.
 */
export function redactPath(pathname: string): string {
  const withoutQuery = pathname.split("?")[0].split("#")[0];
  return withoutQuery
    .split("/")
    .map((segment) => (/^[A-Za-z0-9_-]{24,}$/.test(segment) ? "[redacted]" : segment))
    .join("/");
}

export function buildReport(err: unknown, ctx: { requestId: string; method: string; path: string; status?: number }): ErrorReport {
  const e = (err ?? {}) as { name?: string; message?: string; stack?: string };
  return {
    requestId: ctx.requestId,
    method: ctx.method,
    path: redactPath(ctx.path),
    status: ctx.status ?? 500,
    name: e.name ?? "Error",
    message: e.message ?? String(err),
    stack: e.stack,
  };
}

async function postToWebhook(url: string, report: ErrorReport): Promise<void> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), WEBHOOK_TIMEOUT_MS);
  try {
    await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ service: "slotwise-api", ...report }),
      signal: controller.signal,
    });
  } catch (e) {
    // A monitor that is down is not an application failure.
    logger.warn({ err: (e as Error)?.message, requestId: report.requestId }, "error monitor delivery failed");
  } finally {
    clearTimeout(timer);
  }
}

/** Reports an unhandled error. Never throws; never awaited by the caller. */
export function captureError(
  err: unknown,
  ctx: { requestId: string; method: string; path: string; status?: number },
  env: NodeJS.ProcessEnv = process.env,
): void {
  const report = buildReport(err, ctx);
  logger.error({ ...report, err }, "unhandled error");

  const url = env.ERROR_MONITOR_WEBHOOK_URL;
  if (!url) return;
  // Fire and forget: the response is already being written.
  void postToWebhook(url, report);
}
