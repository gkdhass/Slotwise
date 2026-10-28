import { Request, Response, NextFunction } from "express";
import crypto from "node:crypto";
import { csrfBypassActive } from "../lib/config.js";

const CSRF_COOKIE = "csrf_token";
const CSRF_HEADER = "x-csrf-token";

export function issueCsrf(_req: Request, res: Response, next: NextFunction) {
  if (!res.req?.cookies?.[CSRF_COOKIE]) {
    const token = crypto.randomBytes(24).toString("hex");
    res.cookie(CSRF_COOKIE, token, {
      httpOnly: false,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
    });
  }
  next();
}

export function csrfProtect(req: Request, res: Response, next: NextFunction) {
  // Bypass is only possible in tests, and only when CSRF_DISABLED=true.
  // assertProductionSafety() refuses to start a production process with that flag.
  if (csrfBypassActive()) return next();
  if (["GET", "HEAD", "OPTIONS"].includes(req.method)) return next();
  const cookieToken = req.cookies?.[CSRF_COOKIE];
  const headerToken = req.get(CSRF_HEADER);
  if (!cookieToken || !headerToken || cookieToken !== headerToken) {
    return res.status(403).json({ error: { code: "FORBIDDEN", message: "CSRF token missing or invalid.", requestId: req.id ?? "", fieldErrors: {} } });
  }
  next();
}