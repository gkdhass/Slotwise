import { Router } from "express";
import { z } from "zod";
import { prisma } from "../lib/prisma.js";
import { Errors } from "../lib/errors.js";
import type { AuthedRequest } from "../middleware/auth.js";

const router: Router = Router();

const eventSchema = z.object({
  title: z.string().min(1).max(120),
  description: z.string().optional(),
  durationMinutes: z.number().int().min(5).max(480),
  locationType: z.enum(["custom", "phone", "online"]).default("custom"),
  locationDetails: z.string().optional(),
  timezone: z.string().min(1),
  isPublished: z.boolean().optional(),
});

function slugify(title: string) {
  return title.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") + "-" + Math.random().toString(36).slice(2, 6);
}

router.get("/", async (req: AuthedRequest, res, next) => {
  try {
    const items = await prisma.eventType.findMany({ where: { userId: req.user!.id, archivedAt: null }, orderBy: { createdAt: "desc" } });
    res.json(items);
  } catch (e) { next(e); }
});

router.post("/", async (req: AuthedRequest, res, next) => {
  try {
    const parsed = eventSchema.safeParse(req.body);
    if (!parsed.success) throw parsed.error;
    const data = parsed.data;
    const created = await prisma.eventType.create({
      data: {
        userId: req.user!.id,
        title: data.title,
        slug: slugify(data.title),
        description: data.description,
        durationMinutes: data.durationMinutes,
        locationType: data.locationType,
        locationDetails: data.locationDetails,
        timezone: data.timezone,
        isPublished: data.isPublished ?? false,
      },
    });
    res.status(201).json(created);
  } catch (e) { next(e); }
});

router.get("/:id", async (req: AuthedRequest, res, next) => {
  try {
    const ev = await prisma.eventType.findFirst({ where: { id: String(req.params.id), userId: req.user!.id } });
    if (!ev) throw Errors.notFound();
    res.json(ev);
  } catch (e) { next(e); }
});

router.patch("/:id", async (req: AuthedRequest, res, next) => {
  try {
    const existing = await prisma.eventType.findFirst({ where: { id: String(req.params.id), userId: req.user!.id } });
    if (!existing) throw Errors.notFound();
    const parsed = eventSchema.partial().safeParse(req.body);
    if (!parsed.success) throw parsed.error;
    const data = parsed.data;
    if (data.isPublished === true) {
      const user = await prisma.user.findUnique({ where: { id: req.user!.id } });
      if (!user?.emailVerifiedAt) throw Errors.forbidden();
      const ruleCount = await prisma.availabilityRule.count({ where: { eventTypeId: existing.id } });
      if (ruleCount === 0) {
        throw Errors.unprocessable("Add availability before publishing.", {
          availability: "At least one availability window is required",
        });
      }
    }
    const updated = await prisma.eventType.update({
      where: { id: existing.id },
      data: {
        title: data.title,
        description: data.description,
        durationMinutes: data.durationMinutes,
        locationType: data.locationType,
        locationDetails: data.locationDetails,
        timezone: data.timezone,
        isPublished: data.isPublished,
      },
    });
    res.json(updated);
  } catch (e) { next(e); }
});

router.delete("/:id", async (req: AuthedRequest, res, next) => {
  try {
    const existing = await prisma.eventType.findFirst({ where: { id: String(req.params.id), userId: req.user!.id } });
    if (!existing) throw Errors.notFound();
    await prisma.eventType.update({ where: { id: existing.id }, data: { archivedAt: new Date(), isPublished: false } });
    res.status(204).send();
  } catch (e) { next(e); }
});

// availability GET
router.get("/:id/availability", async (req: AuthedRequest, res, next) => {
  try {
    const existing = await prisma.eventType.findFirst({ where: { id: String(req.params.id), userId: req.user!.id } });
    if (!existing) throw Errors.notFound();
    const rules = await prisma.availabilityRule.findMany({ where: { eventTypeId: existing.id } });
    res.json(rules);
  } catch (e) { next(e); }
});

// availability
router.put("/:id/availability", async (req: AuthedRequest, res, next) => {
  try {
    const existing = await prisma.eventType.findFirst({ where: { id: String(req.params.id), userId: req.user!.id } });
    if (!existing) throw Errors.notFound();
    const rules = z.array(z.object({
      weekday: z.number().int().min(0).max(6),
      startLocal: z.string().regex(/^\d{2}:\d{2}$/),
      endLocal: z.string().regex(/^\d{2}:\d{2}$/),
      timezone: z.string().min(1),
    })).parse(req.body);
    // validate ranges
    for (const r of rules) {
      if (r.startLocal >= r.endLocal) throw Errors.unprocessable("End time must be after start time.", { availability: "invalid range" });
    }
    // reject overlaps within same weekday
    const byDay = new Map<number, typeof rules>();
    for (const r of rules) {
      if (!byDay.has(r.weekday)) byDay.set(r.weekday, []);
      byDay.get(r.weekday)!.push(r);
    }
    for (const [, rs] of byDay) {
      for (let i = 0; i < rs.length; i++) {
        for (let j = i + 1; j < rs.length; j++) {
          if (rs[i].startLocal < rs[j].endLocal && rs[j].startLocal < rs[i].endLocal) {
            throw Errors.unprocessable("Availability windows must not overlap.", { availability: "overlap" });
          }
        }
      }
    }
    await prisma.availabilityRule.deleteMany({ where: { eventTypeId: existing.id } });
    await prisma.availabilityRule.createMany({
      data: rules.map((r) => ({
        eventTypeId: existing.id,
        weekday: r.weekday,
        startLocal: r.startLocal,
        endLocal: r.endLocal,
        timezone: r.timezone,
      })),
    });
    const saved = await prisma.availabilityRule.findMany({ where: { eventTypeId: existing.id } });
    res.json(saved);
  } catch (e) { next(e); }
});

export default router;
