import { Request, Response, NextFunction } from "express";
import crypto from "node:crypto";

export function requestId(req: Request & { id?: string }, _res: Response, next: NextFunction) {
  const id = (req.get("x-request-id") ?? crypto.randomUUID()).toString();
  req.id = id;
  next();
}