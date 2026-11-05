import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { createEvent, createOwner, prisma, purgeUsers } from "./helpers.js";
import {
  DEFAULT_CANCELED_RETENTION_DAYS,
  DEFAULT_COMPLETED_RETENTION_MONTHS,
  purgeExpiredBookings,
  retentionConfig,
} from "../../src/services/retentionPurge.js";

const userIds: string[] = [];

beforeEach(async () => {
  // Also clears fixtures left by an interrupted local run. The test suite uses
  // a real database, so cleanup must not depend only on the in-memory list.
  const stale = await prisma.user.findMany({
    where: { email: { startsWith: "retention-" } },
    select: { id: true },
  });
  await purgeUsers(stale.map((user) => user.id));
});

afterAll(async () => {
  await purgeUsers(userIds);
  await prisma.$disconnect();
});

function monthsBefore(date: Date, months: number): Date {
  const result = new Date(date);
  result.setUTCMonth(result.getUTCMonth() - months);
  return result;
}

async function bookingFixture(input: {
  userId: string;
  eventTypeId: string;
  status: string;
  startAt: Date;
  updatedAt: Date;
  label: string;
}) {
  return prisma.booking.create({
    data: {
      userId: input.userId,
      eventTypeId: input.eventTypeId,
      inviteeName: input.label,
      inviteeEmail: `${input.label.toLowerCase()}-${Math.random().toString(36).slice(2)}@example.test`,
      startAt: input.startAt,
      endAt: new Date(input.startAt.getTime() + 30 * 60_000),
      timezone: "UTC",
      status: input.status,
      idempotencyKey: `retention-${input.label}-${Math.random().toString(36).slice(2)}`,
      createdAt: input.updatedAt,
      updatedAt: input.updatedAt,
    },
  });
}

describe("retention purge", () => {
  it("has the required defaults and rejects malformed overrides", () => {
    expect(retentionConfig({})).toEqual({
      canceledDays: DEFAULT_CANCELED_RETENTION_DAYS,
      completedMonths: DEFAULT_COMPLETED_RETENTION_MONTHS,
      batchSize: 500,
    });
    expect(retentionConfig({ RETENTION_CANCELED_DAYS: "30", RETENTION_COMPLETED_MONTHS: "12", RETENTION_BATCH_SIZE: "10" })).toEqual({
      canceledDays: 30,
      completedMonths: 12,
      batchSize: 10,
    });
    expect(() => retentionConfig({ RETENTION_CANCELED_DAYS: "0" })).toThrow(/RETENTION_CANCELED_DAYS/);
    expect(() => retentionConfig({ RETENTION_COMPLETED_MONTHS: "2.5" })).toThrow(/RETENTION_COMPLETED_MONTHS/);
    expect(() => retentionConfig({ RETENTION_BATCH_SIZE: "abc" })).toThrow(/RETENTION_BATCH_SIZE/);
  });

  it("purges old canceled and completed bookings, including outbox payloads", async () => {
    const { agent, userId } = await createOwner({ prefix: "retention" });
    userIds.push(userId);
    const event = await createEvent(agent, { title: "Retention fixture" });
    const now = new Date("2026-11-05T00:00:00.000Z");
    const oldCanceledAt = new Date(now.getTime() - 91 * 86_400_000);
    const recentCanceledAt = new Date(now.getTime() - 89 * 86_400_000);
    const oldCompletedAt = monthsBefore(now, 25);
    const recentCompletedAt = monthsBefore(now, 23);

    const oldCanceled = await bookingFixture({
      userId,
      eventTypeId: event.id,
      status: "canceled",
      startAt: new Date(oldCanceledAt.getTime() + 60 * 60_000),
      updatedAt: oldCanceledAt,
      label: "old-canceled",
    });
    const recentCanceled = await bookingFixture({
      userId,
      eventTypeId: event.id,
      status: "canceled",
      startAt: new Date(recentCanceledAt.getTime() + 2 * 60 * 60_000),
      updatedAt: recentCanceledAt,
      label: "recent-canceled",
    });
    const oldCompleted = await bookingFixture({
      userId,
      eventTypeId: event.id,
      status: "completed",
      startAt: oldCompletedAt,
      updatedAt: oldCompletedAt,
      label: "old-completed",
    });
    const recentCompleted = await bookingFixture({
      userId,
      eventTypeId: event.id,
      status: "completed",
      startAt: recentCompletedAt,
      updatedAt: recentCompletedAt,
      label: "recent-completed",
    });
    const confirmed = await bookingFixture({
      userId,
      eventTypeId: event.id,
      status: "confirmed",
      startAt: new Date(now.getTime() + 24 * 60 * 60_000),
      updatedAt: now,
      label: "confirmed",
    });
    await prisma.outboxJob.createMany({
      data: [oldCanceled, oldCompleted].map((booking) => ({
        bookingId: booking.id,
        jobType: "booking_confirmation",
        payload: { bookingId: booking.id, inviteeEmail: "retention@example.test" },
      })),
    });

    const result = await purgeExpiredBookings({ now });
    expect(result).toMatchObject({ canceled: 1, completed: 1, total: 2 });

    expect(await prisma.booking.findUnique({ where: { id: oldCanceled.id } })).toBeNull();
    expect(await prisma.booking.findUnique({ where: { id: oldCompleted.id } })).toBeNull();
    expect(await prisma.outboxJob.count({ where: { bookingId: { in: [oldCanceled.id, oldCompleted.id] } } })).toBe(0);
    expect(await prisma.booking.findUnique({ where: { id: recentCanceled.id } })).not.toBeNull();
    expect(await prisma.booking.findUnique({ where: { id: recentCompleted.id } })).not.toBeNull();
    expect(await prisma.booking.findUnique({ where: { id: confirmed.id } })).not.toBeNull();
  });

  it("honors configurable windows and batch size", async () => {
    const { agent, userId } = await createOwner({ prefix: "retention-config" });
    userIds.push(userId);
    const event = await createEvent(agent, { title: "Retention config fixture" });
    const now = new Date("2026-11-05T00:00:00.000Z");
    const old = await bookingFixture({
      userId,
      eventTypeId: event.id,
      status: "canceled",
      startAt: new Date(now.getTime() - 10 * 86_400_000),
      updatedAt: new Date(now.getTime() - 10 * 86_400_000),
      label: "config-old",
    });
    const result = await purgeExpiredBookings({
      now,
      config: { canceledDays: 7, completedMonths: 24, batchSize: 1 },
    });
    expect(result.canceled).toBe(1);
    expect(await prisma.booking.findUnique({ where: { id: old.id } })).toBeNull();
  });
});
