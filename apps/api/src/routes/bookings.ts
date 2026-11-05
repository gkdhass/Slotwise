import { Router } from "express";
import { prisma } from "../lib/prisma.js";
import type { AuthedRequest } from "../middleware/auth.js";

const router: Router = Router();

router.get("/", async (req: AuthedRequest, res, next) => {
  try {
    const status = req.query.status as string | undefined;
    const from = req.query.from ? new Date(String(req.query.from)) : undefined;
    const to = req.query.to ? new Date(String(req.query.to)) : undefined;
    const where: any = { userId: req.user!.id };
    if (status) where.status = status;
    if (from || to) where.startAt = { gte: from, lte: to };
    const items = await prisma.booking.findMany({ where, orderBy: { startAt: "desc" }, include: { eventType: true } });
    res.json(items);
  } catch (e) { next(e); }
});

export default router;
