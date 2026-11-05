import { Router } from "express";
import { z } from "zod";
import { prisma } from "../lib/prisma.js";
import { Errors } from "../lib/errors.js";
import { hashToken } from "../lib/hash.js";
import { now } from "../lib/clock.js";
import { isIanaZone } from "../lib/timezone.js";
import { generateSlots } from "@slotwise/shared";

const router: Router = Router();

/**
 * Loads a booking by management token.
 * Returns null for unknown, expired or malformed tokens so callers can return
 * a single generic denial (never revealing whether the token ever existed).
 */
async function loadBooking(token: string) {
  if (!token || token.length < 16) return null;
  const mt = await prisma.managementToken.findUnique({ where: { tokenHash: hashToken(token) } });
  if (!mt || mt.expiresAt < now()) return null;
  const booking = await prisma.booking.findUnique({ where: { id: mt.bookingId }, include: { eventType: true } });
  if (!booking) return null;
  return { mt, booking };
}



router.get("/:token", async (req, res, next) => {
  try {
    const result = await loadBooking(String(req.params.token));
    if (!result) throw Errors.notFound();
    res.json(result.booking);
  } catch (e) { next(e); }
});

router.post("/:token/cancel", async (req, res, next) => {
  try {
    const result = await loadBooking(String(req.params.token));
    if (!result) throw Errors.notFound(); // generic denial
    const { booking } = result;
    if (booking.status !== "confirmed") return res.json(booking);

    const updated = await prisma.$transaction(async (tx) => {
      const b = await tx.booking.update({
        where: { id: booking.id },
        data: { status: "canceled" },
        include: { eventType: true },
      });
      await tx.outboxJob.create({
        data: {
          bookingId: booking.id,
          jobType: "booking_canceled",
          status: "pending",
          payload: { bookingId: booking.id, to: booking.inviteeEmail },
          availableAt: now(),
        },
      });
      return b;
    });
    res.json(updated);
  } catch (e) { next(e); }
});

router.post("/:token/reschedule", async (req, res, next) => {
  try {
    const result = await loadBooking(String(req.params.token));
    if (!result) throw Errors.notFound();
    const { booking } = result;
    if (booking.status !== "confirmed") {
      throw Errors.conflict("BOOKING_NOT_ACTIVE", "Only confirmed bookings can be rescheduled.");
    }

    const body = z.object({
      startAt: z.string().datetime(),
      timezone: z.string().min(1).optional(),
    }).parse(req.body);
    const tz = body.timezone ?? booking.timezone;
    if (!isIanaZone(tz)) throw Errors.unprocessable("Unknown time zone.", { timezone: "Unknown time zone" });

    const ev = booking.eventType;
    const startAt = new Date(body.startAt);
    const endAt = new Date(startAt.getTime() + ev.durationMinutes * 60000);

    const rules = await prisma.availabilityRule.findMany({ where: { eventTypeId: ev.id } });
    // Only confirmed bookings that can overlap the requested slot matter. Loading
    // the host's whole history (the previous behaviour) made this public endpoint
    // slower every time the host took another booking, for no benefit — the same
    // mistake `public.ts` was fixed for in DEV-25.
    const others = await prisma.booking.findMany({
      where: {
        userId: booking.userId,
        status: "confirmed",
        id: { not: booking.id },
        startAt: { lt: endAt },
        endAt: { gt: startAt },
      },
      select: { startAt: true, endAt: true, status: true },
    });
    const base = {
      rules: rules.map((r) => ({ weekday: r.weekday, startLocal: r.startLocal, endLocal: r.endLocal })),
      durationMinutes: ev.durationMinutes,
      eventTimezone: ev.timezone,
      displayTimezone: tz,
      from: startAt,
      to: endAt,
      now: now(),
    };
    const onGrid = generateSlots({ ...base, existingBookings: [] }).some((s) => s.startAt === startAt.toISOString());
    if (!onGrid) {
      throw Errors.unprocessable("That time is not one of this event's available slots.", {
        startAt: "Choose a slot from the event page",
      });
    }
    const free = generateSlots({
      ...base,
      existingBookings: others.map((b) => ({
        startAt: b.startAt.toISOString(),
        endAt: b.endAt.toISOString(),
        status: b.status,
      })),
    }).some((s) => s.startAt === startAt.toISOString());
    if (!free) throw Errors.slotUnavailable();

    // The row keeps its identity: the exclusion constraint atomically swaps the
    // range. If the destination is taken the UPDATE fails and the old slot stays.
    try {
      const updated = await prisma.$transaction(async (tx) => {
        const b = await tx.booking.update({
          where: { id: booking.id },
          data: { startAt, endAt, timezone: tz },
          include: { eventType: true },
        });
        await tx.outboxJob.create({
          data: {
            bookingId: booking.id,
            jobType: "booking_rescheduled",
            status: "pending",
            payload: { bookingId: booking.id, to: booking.inviteeEmail, startAt: startAt.toISOString() },
            availableAt: now(),
          },
        });
        return b;
      });
      res.json(updated);
    } catch (e: any) {
      const full = JSON.stringify(e, Object.getOwnPropertyNames(e));
      if (full.includes("23P01") || full.includes("40P01") || full.includes("bookings_no_host_overlap")) {
        throw Errors.slotUnavailable();
      }
      throw e;
    }
  } catch (e) { next(e); }
});

export default router;
