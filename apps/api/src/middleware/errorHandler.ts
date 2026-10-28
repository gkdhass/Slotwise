import { Request, Response, NextFunction } from "express";
import { AppError } from "../lib/errors.js";
import { Prisma } from "@prisma/client";

export function errorHandler(err: any, req: Request & { id?: string }, res: Response, _next: NextFunction) {
  const requestId = req.id ?? "";
  // Prisma unique violation / exclusion constraint
  if (err?.code === "P2002") {
    return res.status(409).json({ error: { code: "CONFLICT", message: "Conflict.", requestId, fieldErrors: {} } });
  }
  if (err?.code === "P2003") {
    return res.status(409).json({ error: { code: "CONFLICT", message: "Conflict.", requestId, fieldErrors: {} } });
  }
  // Raw pg error for exclusion constraint (SQLSTATE 23P01) surfaces via Prisma query error with code P2010? 
  // Detect by message/code
  const msg = String(err?.message ?? "");
  if (msg.includes("23P01") || msg.includes("40P01") || msg.includes("deadlock") || msg.includes("bookings_no_host_overlap") || msg.includes("exclusion constraint")) {
    return res.status(409).json({ error: { code: "SLOT_UNAVAILABLE", message: "That time is no longer available. Choose another slot.", requestId, fieldErrors: {} } });
  }
  if (err instanceof AppError) {
    return res.status(err.status).json({ error: { code: err.code, message: err.message, requestId, fieldErrors: err.fieldErrors } });
  }
  // Zod validation errors
  if (err?.name === "ZodError") {
    const fieldErrors: Record<string, string> = {};
    for (const issue of err.issues ?? []) {
      const path = (issue.path ?? []).join(".") || "form";
      fieldErrors[path] = issue.message;
    }
    return res.status(400).json({ error: { code: "VALIDATION_ERROR", message: "Check the highlighted fields and try again.", requestId, fieldErrors } });
  }
  console.error("[error]", requestId, err);
  return res.status(500).json({ error: { code: "INTERNAL", message: "Unexpected server error.", requestId, fieldErrors: {} } });
}