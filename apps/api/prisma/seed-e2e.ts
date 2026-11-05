import "dotenv/config";
import { PrismaClient } from "@prisma/client";
import argon2 from "argon2";

/**
 * Deterministic fixture for the Playwright suite (real API + real database).
 * Idempotent: safe to run before every E2E run.
 */
const prisma = new PrismaClient();

export const E2E_OWNER = { email: "e2e.owner@slotwise.test", password: "e2e-password-123" };
export const E2E_SLUG = "intro-tutoring";

async function main() {
  const passwordHash = await argon2.hash(E2E_OWNER.password, { type: argon2.argon2id });
  const user = await prisma.user.upsert({
    where: { email: E2E_OWNER.email },
    update: { passwordHash, emailVerifiedAt: new Date(), deletedAt: null },
    create: {
      email: E2E_OWNER.email,
      passwordHash,
      role: "owner",
      emailVerifiedAt: new Date(),
    },
  });

  // Reset bookings/tokens/outbox for a clean loop.
  await prisma.outboxJob.deleteMany({ where: { booking: { userId: user.id } } });
  await prisma.booking.deleteMany({ where: { userId: user.id } });
  await prisma.eventType.deleteMany({ where: { userId: user.id } });

  const event = await prisma.eventType.create({
    data: {
      userId: user.id,
      title: "Intro tutoring",
      slug: E2E_SLUG,
      description: "A 30 minute introductory tutoring call.",
      durationMinutes: 30,
      locationType: "online",
      locationDetails: "Video link sent after booking",
      timezone: "Asia/Kolkata",
      isPublished: true,
      availability: {
        create: [1, 2, 3, 4, 5].map((weekday) => ({
          weekday,
          startLocal: "09:00",
          endLocal: "17:00",
          timezone: "Asia/Kolkata",
        })),
      },
    },
  });

  // A second event type on the same host, used for cross-event overlap checks.
  await prisma.eventType.create({
    data: {
      userId: user.id,
      title: "Deep dive",
      slug: "deep-dive",
      description: "A 60 minute session.",
      durationMinutes: 60,
      locationType: "online",
      timezone: "Asia/Kolkata",
      isPublished: true,
      availability: {
        create: [1, 2, 3, 4, 5].map((weekday) => ({
          weekday,
          startLocal: "09:00",
          endLocal: "17:00",
          timezone: "Asia/Kolkata",
        })),
      },
    },
  });

  console.log(JSON.stringify({ owner: E2E_OWNER.email, eventId: event.id, slug: event.slug }));
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
