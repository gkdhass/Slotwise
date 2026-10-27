import { Router } from "express";
import { z } from "zod";
import { prisma } from "../lib/prisma.js";
import { Errors } from "../lib/errors.js";
import { generateSlots } from "@slotwise/shared";
import { randomToken, hashToken } from "../lib/hash.js";

const router: Router = Router();

router.get("/:slug", async (req, res, next) => {
  try {
    const ev = await prisma.eventType.findUnique({ where: { slug: req.params.slug } });
    if (!ev || !ev.isPublished || ev.archivedAt) throw Errors.notFound();
    res.json({
      slug: ev.slug,
      title: ev.title,
      description: ev.description,
      durationMinutes: ev.durationMinutes,
      locationType: ev.locationType,
      locationDetails: ev.locationDetails,
      timezone: ev.timezone,
    });
  } catch (e) { next(e); }
});

router.get("/:slug/slots", async (req, res, next) => {
  try {
    const ev = await prisma.eventType.findUnique({ where: { slug: req.params.slug } });
    if (!ev || !ev.isPublished || ev.archivedAt) throw Errors.notFound();
    const from = z.string().datetime().parse(req.query.from);
    const to = z.string().datetime().parse(req.query.to);
    const tz = z.string().min(1).parse(req.query.tz ?? ev.timezone);
    const rules = await prisma.availabilityRule.findMany({ where: { eventTypeId: ev.id } });
    const bookings = await prisma.booking.findMany({ where: { eventTypeId: ev.id, status: "confirmed" } });
    const slots = generateSlots({
      rules: rules.map((r) => ({ weekday: r.weekday, startLocal: r.startLocal, endLocal: r.endLocal })),
      durationMinutes: ev.durationMinutes,
      eventTimezone: ev.timezone,
      displayTimezone: tz,
      from: new Date(from),
      to: new Date(to),
      existingBookings: bookings.map((b) => ({ startAt: b.startAt.toISOString(), endAt: b.endAt.toISOString(), status: b.status })),
      now: new Date(),
    });
    res.json(slots);
  } catch (e) { next(e); }
});

const bookingSchema = z.object({
  startAt: z.string().datetime(),
  timezone: z.string().min(1),
  invitee: z.object({
    name: z.string().min(1).max(120),
    email: z.string().email(),
    note: z.string().optional(),
  }),
  idempotencyKey: z.string().min(1),
});

router.post("/:slug/bookings", async (req, res, next) => {
  try {
    const parsed = bookingSchema.safeParse(req.body);
    if (!parsed.success) throw parsed.error;
    const data = parsed.data;
    const ev = await prisma.eventType.findUnique({ where: { slug: req.params.slug } });
    if (!ev || !ev.isPublished || ev.archivedAt) throw Errors.notFound();

    // idempotency check
    const existing = await prisma.booking.findFirst({
      where: { userId: ev.userId, idempotencyKey: data.idempotencyKey },
    });
    if (existing) {
      const token = await prisma.managementToken.findFirst({ where: { bookingId: existing.id } });
      return res.status(200).json({
        reference: existing.id, // use id as reference for now
        booking: existing,
        managementToken: token?.tokenHash ?? null,
      });
    }

    const startAt = new Date(data.startAt);
    const endAt = new Date(startAt.getTime() + ev.durationMinutes * 60000);

    // validate slot is a valid slot
    const rules = await prisma.availabilityRule.findMany({ where: { eventTypeId: ev.id } });
    const bookings = await prisma.booking.findMany({ where: { eventTypeId: ev.id, status: "confirmed" } });
    const slots = generateSlots({
      rules: rules.map((r) => ({ weekday: r.weekday, startLocal: r.startLocal, endLocal: r.endLocal })),
      durationMinutes: ev.durationMinutes,
      eventTimezone: ev.timezone,
      displayTimezone: data.timezone,
      from: startAt,
      to: endAt,
      existingBookings: bookings.map((b) => ({ startAt: b.startAt.toISOString(), endAt: b.endAt.toISOString(), status: b.status })),
      now: new Date(Date.now() - 60000),
    });
    const valid = slots.some((s) => s.startAt === startAt.toISOString());
    if (!valid) throw Errors.validation("Invalid slot.");

    // transaction
    let booking: any;
    let rawToken: string = "";
    try {
      const result = await prisma.$transaction(async (tx) => {
        const b = await tx.booking.create({
          data: {
            userId: ev.userId,
            eventTypeId: ev.id,
            inviteeName: data.invitee.name,
            inviteeEmail: data.invitee.email,
            inviteeNote: data.invitee.note,
            startAt,
            endAt,
            timezone: data.timezone,
            status: "confirmed",
            idempotencyKey: data.idempotencyKey,
          },
        });
        const rt = randomToken();
        await tx.managementToken.create({
          data: {
            bookingId: b.id,
            tokenHash: hashToken(rt),
            expiresAt: new Date(Date.now() + 1000 * 60 * 60 * 24 * 30),
          },
        });
        await tx.outboxJob.create({
          data: {
            bookingId: b.id,
            jobType: "booking_confirmation",
            status: "pending",
            payload: { bookingId: b.id, to: data.invitee.email },
            availableAt: new Date(),
          },
        });
        return { b, rt };
      }, { timeout: 15000 });
      booking = result.b;
      rawToken = result.rt;
    } catch (e: any) {
      const full = JSON.stringify(e, Object.getOwnPropertyNames(e));
      if (e?.code === "P2002" || full.includes("P2002")) {
        const ex = await prisma.booking.findFirst({ where: { userId: ev.userId, idempotencyKey: data.idempotencyKey } });
        if (ex) {
          return res.status(200).json({ reference: ex.id, booking: ex, managementToken: null });
        }
      }
      if (full.includes("23P01") || full.includes("40P01") || full.includes("deadlock") || full.includes("bookings_no_host_overlap") || full.includes("exclusion")) {
        throw Errors.slotUnavailable();
      }
      throw e;
    }

    res.status(201).json({
      reference: booking.id,
      booking: booking,
      managementToken: rawToken,
    });
  } catch (e) { next(e); }
});

export default router;
