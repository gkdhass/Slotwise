import { Request, Response, NextFunction } from "express";
import { AppError } from "../lib/errors.js";
import { captureError } from "../lib/errorMonitor.js";

function isExclusionViolation(err: unknown): boolean {
  const text = (() => {
    try {
      return JSON.stringify(err, Object.getOwnPropertyNames(err as object));
    } catch {
      return String(err);
    }
  })();
  return (
    text.includes("23P01") ||
    text.includes("40P01") ||
    text.includes("deadlock") ||
    text.includes("bookings_no_host_overlap") ||
    text.includes("exclusion constraint") ||
    text.includes("conflicting key value violates exclusion")
  );
}

export function errorHandler(err: any, req: Request & { id?: string }, res: Response, _next: NextFunction) {
  const requestId = req.id ?? "";

  if (err instanceof AppError) {
    return res
      .status(err.status)
      .json({ error: { code: err.code, message: err.message, requestId, fieldErrors: err.fieldErrors } });
  }

  if (err?.name === "ZodError") {
    const fieldErrors: Record<string, string> = {};
    for (const issue of err.issues ?? []) {
      const path = (issue.path ?? []).join(".") || "form";
      fieldErrors[path] = issue.message;
    }
    return res.status(400).json({
      error: {
        code: "VALIDATION_ERROR",
        message: "Check the highlighted fields and try again.",
        requestId,
        fieldErrors,
      },
    });
  }

  if (isExclusionViolation(err)) {
    return res.status(409).json({
      error: {
        code: "SLOT_UNAVAILABLE",
        message: "That time is no longer available. Choose another slot.",
        requestId,
        fieldErrors: {},
      },
    });
  }

  if (err?.code === "P2002") {
    return res
      .status(409)
      .json({ error: { code: "CONFLICT", message: "Conflict.", requestId, fieldErrors: {} } });
  }
  if (err?.code === "P2003") {
    return res
      .status(409)
      .json({ error: { code: "CONFLICT", message: "Conflict.", requestId, fieldErrors: {} } });
  }
  if (err?.code === "P2025") {
    return res
      .status(404)
      .json({ error: { code: "NOT_FOUND", message: "Resource not found.", requestId, fieldErrors: {} } });
  }

  // Structured log + optional monitor webhook, never a bare console dump.
  captureError(err, { requestId, method: req.method, path: req.originalUrl, status: 500 });
  return res.status(500).json({
    error: { code: "INTERNAL", message: "Unexpected server error.", requestId, fieldErrors: {} },
  });
}
