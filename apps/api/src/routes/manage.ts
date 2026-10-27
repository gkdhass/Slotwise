import { Router } from "express";
import { z } from "zod";
import { prisma } from "../lib/prisma.js";
import { Errors } from "../lib/errors.js";
import { hashToken } from "../lib/hash.js";

const router: Router = Router();

async function loadBooking(token: string) {
  const mt = await prisma.managementToken.findUnique({ where: { tokenHash: hashToken(token) } });
  if (!mt || mt.expiresAt < new Date()) return null;
  const booking = await prisma.booking.findUnique({ where: { id: mt.bookingId } });
  return { mt, booking };
}

router.post("/:token/cancel", async (req, res, next) => {
  try {
    const result = await loadBooking(req.params.token);
    if (!result || !result.booking) throw Errors.notFound(); // generic denial
    const { booking } = result;
    if (booking.status !== "confirmed") {
      return res.json(booking);
    }
    const updated = await prisma.booking.update({ where: { id: booking.id }, data: { status: "canceled" } });
    await prisma.outboxJob.create({ data: { bookingId: booking.id, jobType: "booking_canceled", status: "pending", payload: {}, availableAt: new Date() } });
    res.json(updated);
  } catch (e) { next(e); }
});

router.post("/:token/reschedule", async (req, res, next) => {
  try {
    const result = await loadBooking(req.params.token);
    if (!result || !result.booking) throw Errors.notFound();
    const { booking } = result;
    const newStart = z.string().datetime().parse(req.body?.startAt);
    const tz = z.string().min(1).parse(req.body?.timezone ?? booking.timezone);
    const ev = await prisma.eventType.findUnique({ where: { id: booking.eventTypeId } });
    if (!ev) throw Errors.notFound();
    const endAt = new Date(new Date(newStart).getTime() + ev.durationMinutes * 60000);

    // check conflict (excluding current booking)
    const conflict = await prisma.booking.findFirst({
      where: {
        eventTypeId: booking.eventTypeId,
        status: "confirmed",
        id: { not: booking.id },
        startAt: { lt: endAt },
        endAt: { gt: new Date(newStart) },
      },
    });
    if (conflict) throw Errors.slotUnavailable();

    // reserve new slot first (update in transaction protected by constraint)
    const updated = await prisma.$transaction(async (tx) => {
      const b = await tx.booking.update({
        where: { id: booking.id },
        data: { startAt: new Date(newStart), endAt, timezone: tz },
      });
      await tx.outboxJob.create({ data: { bookingId: booking.id, jobType: "booking_rescheduled", status: "pending", payload: {}, availableAt: new Date() } });
      return b;
    });
    res.json(updated);
  } catch (e) { next(e); }
});

export default router;
