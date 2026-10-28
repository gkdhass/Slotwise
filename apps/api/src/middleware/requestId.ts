import { Request, Response, NextFunction } from "express";
import crypto from "node:crypto";

/**
 * Request correlation (NFR-05).
 *
 * Every request gets an id. A well-formed `x-request-id` from the caller is
 * kept so a browser, proxy or load balancer can correlate its own logs; anything
 * else is replaced with a fresh UUID. The id is echoed back in the response
 * header and in every error envelope, so a user can quote it and an operator can
 * find the exact log line.
 *
 * The incoming value is validated before use: an arbitrary header string would
 * otherwise be written into logs and response headers, which is a log/header
 * injection vector.
 */

/** Printable, bounded, no whitespace or control characters. */
const SAFE_REQUEST_ID = /^[A-Za-z0-9._:-]{8,128}$/;

export function normaliseRequestId(incoming: string | undefined): string {
  return incoming && SAFE_REQUEST_ID.test(incoming) ? incoming : crypto.randomUUID();
}

export function requestId(req: Request & { id?: string }, res: Response, next: NextFunction) {
  const id = normaliseRequestId(req.get("x-request-id"));
  req.id = id;
  res.setHeader("x-request-id", id);
  next();
}
