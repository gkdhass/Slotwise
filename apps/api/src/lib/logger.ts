import pino, { type Logger, type LoggerOptions } from "pino";

/**
 * Structured logging (NFR-05).
 *
 * Every line is JSON with at least `level`, `time`, `msg` and, for HTTP
 * requests, `req.id` — the same value the client sees in the `x-request-id`
 * response header and in an error envelope's `requestId`.
 *
 * Redaction is centralised here rather than left to call sites: session
 * cookies, CSRF tokens, worker secrets and any password field are replaced
 * with `[Redacted]` before the line is written. Security hygiene rule: never
 * log passwords or tokens, even at debug level.
 */

/** Header/body paths that must never reach the log. */
export const REDACT_PATHS = [
  "req.headers.authorization",
  "req.headers.cookie",
  "req.headers['x-csrf-token']",
  "req.headers['x-worker-secret']",
  "res.headers['set-cookie']",
  "password",
  "currentPassword",
  "newPassword",
  "token",
  "tokenHash",
  "req.body.password",
  "req.body.currentPassword",
  "req.body.newPassword",
  "req.body.token",
];

export const CENSOR = "[Redacted]";

export function loggerOptions(level = defaultLevel()): LoggerOptions {
  return {
    level,
    redact: { paths: REDACT_PATHS, censor: CENSOR },
    base: { service: "slotwise-api" },
    timestamp: pino.stdTimeFunctions.isoTime,
  };
}

/**
 * `silent` under NODE_ENV=test: a test run should fail on an assertion, not
 * scroll past thousands of JSON lines. Overridable with LOG_LEVEL everywhere
 * else (default `info`).
 */
function defaultLevel(): string {
  if (process.env.NODE_ENV === "test") return "silent";
  return process.env.LOG_LEVEL ?? "info";
}

/** Builds a logger. `destination` exists so tests can capture the output. */
export function createLogger(destination?: NodeJS.WritableStream, level?: string): Logger {
  const opts = loggerOptions(level);
  return destination ? pino(opts, destination) : pino(opts);
}

export const logger = createLogger();
