import type { Prisma } from "@prisma/client";
import { prisma } from "../lib/prisma.js";

export const DEFAULT_CANCELED_RETENTION_DAYS = 90;
export const DEFAULT_COMPLETED_RETENTION_MONTHS = 24;
export const DEFAULT_RETENTION_BATCH_SIZE = 500;

export type RetentionConfig = {
  canceledDays: number;
  completedMonths: number;
  batchSize: number;
};

function positiveInteger(raw: string | undefined, fallback: number, name: string): number {
  if (raw === undefined || raw.trim() === "") return fallback;
  if (!/^\d+$/.test(raw.trim()) || Number(raw) < 1 || !Number.isSafeInteger(Number(raw))) {
    throw new Error(`${name} must be a positive integer`);
  }
  return Number(raw);
}

/** Reads retention windows without silently accepting a malformed deployment value. */
export function retentionConfig(env: NodeJS.ProcessEnv = process.env): RetentionConfig {
  return {
    canceledDays: positiveInteger(env.RETENTION_CANCELED_DAYS, DEFAULT_CANCELED_RETENTION_DAYS, "RETENTION_CANCELED_DAYS"),
    completedMonths: positiveInteger(
      env.RETENTION_COMPLETED_MONTHS,
      DEFAULT_COMPLETED_RETENTION_MONTHS,
      "RETENTION_COMPLETED_MONTHS",
    ),
    batchSize: positiveInteger(env.RETENTION_BATCH_SIZE, DEFAULT_RETENTION_BATCH_SIZE, "RETENTION_BATCH_SIZE"),
  };
}

function monthsBefore(date: Date, months: number): Date {
  const result = new Date(date);
  result.setUTCMonth(result.getUTCMonth() - months);
  return result;
}

export type PurgeResult = {
  canceled: number;
  completed: number;
  total: number;
  canceledBefore: Date;
  completedBefore: Date;
};

/**
 * Deletes only terminal bookings outside their configured windows.
 *
 * Cancellation age uses `updatedAt`, which is changed by the cancellation
 * route. Completion age uses `endAt`, the point at which the appointment's
 * record is no longer operationally current. Outbox rows are removed first;
 * their FK is SetNull by design for normal booking deletion, but retention
 * deletion must remove the queued payload as well rather than leave invitee
 * data behind.
 */
export async function purgeExpiredBookings(
  options: { now?: Date; config?: RetentionConfig; db?: Pick<typeof prisma, "$transaction"> } = {},
): Promise<PurgeResult> {
  const now = options.now ?? new Date();
  const config = options.config ?? retentionConfig();
  const canceledBefore = new Date(now.getTime() - config.canceledDays * 86_400_000);
  const completedBefore = monthsBefore(now, config.completedMonths);
  const db = options.db ?? prisma;

  return db.$transaction(async (tx: Prisma.TransactionClient) => {
    const [canceled, completed] = await Promise.all([
      tx.booking.findMany({
        where: { status: "canceled", updatedAt: { lt: canceledBefore } },
        select: { id: true },
        orderBy: { updatedAt: "asc" },
        take: config.batchSize,
      }),
      tx.booking.findMany({
        where: { status: "completed", endAt: { lt: completedBefore } },
        select: { id: true },
        orderBy: { endAt: "asc" },
        take: config.batchSize,
      }),
    ]);

    const ids = [...canceled, ...completed].map((booking) => booking.id);
    if (ids.length > 0) {
      await tx.outboxJob.deleteMany({ where: { bookingId: { in: ids } } });
      await tx.booking.deleteMany({ where: { id: { in: ids } } });
    }

    return {
      canceled: canceled.length,
      completed: completed.length,
      total: ids.length,
      canceledBefore,
      completedBefore,
    };
  });
}
