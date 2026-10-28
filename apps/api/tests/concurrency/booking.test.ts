import { describe, it, expect, beforeAll, afterAll } from "vitest";
import request from "supertest";
import app from "../../src/index.js";
import { prisma } from "../../src/lib/prisma.js";
import { hashPassword } from "../../src/lib/hash.js";

describe("concurrency: no double bookings", () => {
  let cookie: string;
  let userId: string;
  let slugA: string;
  let slugB: string;
  const slotStart = "2026-12-01T10:00:00.000Z";

  beforeAll(async () => {
    const email = "conc@example.test";
    const existing = await prisma.user.findMany({ where: { email } });
    for (const u of existing) {
      await prisma.booking.deleteMany({ where: { userId: u.id } });
      await prisma.eventType.deleteMany({ where: { userId: u.id } });
    }
    await prisma.user.deleteMany({ where: { email } });
    const hash = await hashPassword("password123");
    const user = await prisma.user.create({ data: { email, passwordHash: hash, role: "owner", emailVerifiedAt: new Date() } });
    userId = user.id;
    const evA = await prisma.eventType.create({ data: { userId, title: "A", slug: "conc-a", durationMinutes: 30, timezone: "UTC", isPublished: true } });
    const evB = await prisma.eventType.create({ data: { userId, title: "B", slug: "conc-b", durationMinutes: 30, timezone: "UTC", isPublished: true } });
    slugA = evA.slug;
    slugB = evB.slug;
    await prisma.availabilityRule.createMany({
      data: [
        { eventTypeId: evA.id, weekday: 2, startLocal: "00:00", endLocal: "23:59", timezone: "UTC" },
        { eventTypeId: evB.id, weekday: 2, startLocal: "00:00", endLocal: "23:59", timezone: "UTC" },
      ],
    });
    const login = await request(app).post("/api/v1/auth/login").send({ email, password: "password123" });
    cookie = login.headers["set-cookie"][0];
  });

  afterAll(async () => {
    await prisma.booking.deleteMany({ where: { user: { email: "conc@example.test" } } });
    await prisma.eventType.deleteMany({ where: { user: { email: "conc@example.test" } } });
    await prisma.user.deleteMany({ where: { email: "conc@example.test" } });
    await prisma.$disconnect();
  });

  it("50 parallel requests for the same slot -> exactly one confirmed booking", async () => {
    const reqs = Array.from({ length: 50 }, (_, i) =>
      request(app)
        .post(`/api/v1/public/${slugA}/bookings`)
        .send({ startAt: slotStart, timezone: "UTC", invitee: { name: `u${i}`, email: `u${i}@example.test` }, idempotencyKey: `k-${i}` }),
    );
    const results = await Promise.all(reqs);
    const ok = results.filter((r) => r.status === 201 || r.status === 200);
    const dbCount = await prisma.booking.count({ where: { userId, status: "confirmed", startAt: new Date(slotStart) } });
    // NFR-03: exactly one confirmed booking; all others must not be confirmed (409 or 5xx treated as rejected)
    expect(ok.length).toBe(1);
    expect(dbCount).toBe(1);
    const count = await prisma.booking.count({ where: { userId, status: "confirmed", startAt: new Date(slotStart) } });
    expect(count).toBe(1);
  });

  it("overlapping slots across two event types -> at most one confirmed booking", async () => {
    const start2 = "2026-12-01T10:15:00.000Z";
    const reqs = [
      ...Array.from({ length: 25 }, (_, i) =>
        request(app).post(`/api/v1/public/${slugA}/bookings`).send({ startAt: slotStart, timezone: "UTC", invitee: { name: `a${i}`, email: `a${i}@example.test` }, idempotencyKey: `ka-${i}` }),
      ),
      ...Array.from({ length: 25 }, (_, i) =>
        request(app).post(`/api/v1/public/${slugB}/bookings`).send({ startAt: start2, timezone: "UTC", invitee: { name: `b${i}`, email: `b${i}@example.test` }, idempotencyKey: `kb-${i}` }),
      ),
    ];
    const results = await Promise.all(reqs);
    const ok = results.filter((r) => r.status === 201 || r.status === 200);
    // overlapping ranges: at most one confirmed among both
    expect(ok.length).toBeLessThanOrEqual(1);
  });
});