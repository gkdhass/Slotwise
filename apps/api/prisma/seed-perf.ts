import "dotenv/config";
import { PrismaClient } from "@prisma/client";
import argon2 from "argon2";

/**
 * Deterministic fixture for the load test (scripts/load.mjs).
 *
 * Idempotent: re-running keeps exactly one published event with a wide
 * availability window, so the slots endpoint always has a realistic grid to
 * serialise. Bookings are cleared so the response size stays stable between
 * runs and results are comparable.
 */
const prisma = new PrismaClient();

export const PERF_OWNER = { email: "perf.load@slotwise.test", password: "perf-load-password-123" };
export const PERF_SLUG = "perf-load-test";

async function main() {
  const passwordHash = await argon2.hash(PERF_OWNER.password, { type: argon2.argon2id });
  const user = await prisma.user.upsert({
    where: { email: PERF_OWNER.email },
    update: { passwordHash, emailVerifiedAt: new Date(), deletedAt: null },
    create: {
      email: PERF_OWNER.email,
      passwordHash,
      role: "owner",
      emailVerifiedAt: new Date(),
    },
  });

  await prisma.outboxJob.deleteMany({ where: { booking: { userId: user.id } } });
  await prisma.booking.deleteMany({ where: { userId: user.id } });
  await prisma.eventType.deleteMany({ where: { userId: user.id } });

  const event = await prisma.eventType.create({
    data: {
      userId: user.id,
      title: "Load test consultation",
      slug: PERF_SLUG,
      description: "Fixture for the NFR-01 load test.",
      durationMinutes: 30,
      locationType: "online",
      locationDetails: "Video link sent after booking",
      timezone: "Asia/Kolkata",
      isPublished: true,
      // Every day, all day: the slots endpoint never returns an empty grid.
      availability: {
        create: [0, 1, 2, 3, 4, 5, 6].map((weekday) => ({
          weekday,
          startLocal: "00:00",
          endLocal: "23:59",
          timezone: "Asia/Kolkata",
        })),
      },
    },
  });

  console.log(JSON.stringify({ owner: PERF_OWNER.email, eventId: event.id, slug: event.slug }));
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
