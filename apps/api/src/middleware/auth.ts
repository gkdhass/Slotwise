import { Request, Response, NextFunction } from "express";
import { getSessionUser } from "../services/authService.js";

export interface AuthedRequest extends Request {
  user?: { id: string; email: string; role: string; emailVerifiedAt: Date | null };
}

export async function loadSession(req: AuthedRequest, _res: Response, next: NextFunction) {
  const raw = req.cookies?.session;
  const user = await getSessionUser(raw);
  if (user) {
    req.user = { id: user.id, email: user.email, role: user.role, emailVerifiedAt: user.emailVerifiedAt };
  }
  next();
}

export function requireAuth(req: AuthedRequest, res: Response, next: NextFunction) {
  if (!req.user) {
    return res.status(401).json({ error: { code: "UNAUTHORIZED", message: "Authentication required.", requestId: (req as any).id ?? "", fieldErrors: {} } });
  }
  next();
}