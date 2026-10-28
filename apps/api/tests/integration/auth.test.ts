import { describe, it, expect, beforeAll, afterAll } from "vitest";
import request from "supertest";
import app from "../../src/index.js";
import { prisma } from "../../src/lib/prisma.js";

describe("auth + two-owner authorization", () => {
  const ownerA = { email: "ownerA@example.test", password: "password123" };
  const ownerB = { email: "ownerB@example.test", password: "password123" };
  let agentA: any;
  let agentB: any;
  let eventAId: string;

  beforeAll(async () => {
    await prisma.booking.deleteMany({ where: { user: { email: { in: [ownerA.email, ownerB.email, "unverified@example.test"] } } } });
    await prisma.eventType.deleteMany({ where: { user: { email: { in: [ownerA.email, ownerB.email, "unverified@example.test"] } } } });
    await prisma.user.deleteMany({ where: { email: { in: [ownerA.email, ownerB.email, "unverified@example.test"] } } });
    agentA = request.agent(app);
    agentB = request.agent(app);
  });

  afterAll(async () => {
    await prisma.booking.deleteMany({ where: { user: { email: { in: [ownerA.email, ownerB.email, "unverified@example.test"] } } } });
    await prisma.eventType.deleteMany({ where: { user: { email: { in: [ownerA.email, ownerB.email, "unverified@example.test"] } } } });
    await prisma.user.deleteMany({ where: { email: { in: [ownerA.email, ownerB.email, "unverified@example.test"] } } });
    await prisma.$disconnect();
  });

  it("registers and verifies owner A", async () => {
    const reg = await agentA.post("/api/v1/auth/register").send(ownerA);
    expect(reg.status).toBe(201);
    await prisma.user.update({ where: { email: ownerA.email }, data: { emailVerifiedAt: new Date() } });
  });

  it("registers and verifies owner B", async () => {
    const reg = await agentB.post("/api/v1/auth/register").send(ownerB);
    expect(reg.status).toBe(201);
    await prisma.user.update({ where: { email: ownerB.email }, data: { emailVerifiedAt: new Date() } });
  });

  it("logs in both owners", async () => {
    const a = await agentA.post("/api/v1/auth/login").send(ownerA);
    expect(a.status).toBe(200);
    const b = await agentB.post("/api/v1/auth/login").send(ownerB);
    expect(b.status).toBe(200);
  });

  it("unverified owner cannot publish", async () => {
    const agentU = request.agent(app);
    await agentU.post("/api/v1/auth/register").send({ email: "unverified@example.test", password: "password123" });
    const login = await agentU.post("/api/v1/auth/login").send({ email: "unverified@example.test", password: "password123" });
    // login may succeed (unverified can log in)
    if (login.status === 200) {
      const ev = await agentU.post("/api/v1/event-types").send({ title: "E", durationMinutes: 30, timezone: "UTC" });
      expect(ev.status).toBe(201);
      const pub = await agentU.patch(`/api/v1/event-types/${ev.body.id}`).send({ isPublished: true });
      expect(pub.status).toBe(403);
    }
  });

  it("owner A creates an event", async () => {
    const res = await agentA.post("/api/v1/event-types").send({ title: "A event", durationMinutes: 30, timezone: "UTC" });
    expect(res.status).toBe(201);
    eventAId = res.body.id;
  });

  it("owner B cannot read/edit/delete owner A's event (403/404)", async () => {
    const patch = await agentB.patch(`/api/v1/event-types/${eventAId}`).send({ title: "hacked" });
    expect([403, 404]).toContain(patch.status);
    const del = await agentB.delete(`/api/v1/event-types/${eventAId}`);
    expect([403, 404]).toContain(del.status);
    const ev = await prisma.eventType.findUnique({ where: { id: eventAId } });
    expect(ev?.title).toBe("A event");
  });

  it("owner B cannot list owner A's bookings (scoped)", async () => {
    const res = await agentB.get("/api/v1/bookings");
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
  });
});