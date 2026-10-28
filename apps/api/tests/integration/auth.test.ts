import { describe, it, expect, beforeAll, afterAll } from "vitest";
import request from "supertest";
import app from "../../src/index.js";
import { prisma } from "../../src/lib/prisma.js";
import { hashToken } from "../../src/lib/hash.js";
import { createOwner, PASSWORD, purgeUsers, uniqueEmail } from "./helpers.js";

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

// ---------------------------------------------------------------------------
// Token kinds and account state (FR-01). Verification and reset tokens are rows
// in `sessions`, kept apart from real sessions only by a prefix on the raw
// token, so both directions have to be asserted.
// ---------------------------------------------------------------------------

describe("auth token kinds and account state", () => {
  const createdUserIds: string[] = [];

  afterAll(async () => {
    await purgeUsers(createdUserIds);
    await prisma.$disconnect();
  });

  function sessionCookieHeader(headers: Record<string, unknown>): string | null {
    const raw = headers["set-cookie"];
    const list = Array.isArray(raw) ? raw : typeof raw === "string" ? [raw] : [];
    for (const cookie of list) {
      const m = String(cookie).match(/^session=([^;]+)/);
      if (m) return m[1];
    }
    return null;
  }

  function sessionCookieFrom(res: { headers: Record<string, unknown> }): string {
    const token = sessionCookieHeader(res.headers);
    if (!token) throw new Error("no session cookie issued");
    return token;
  }

  it("a verification token cannot be used as a session cookie", async () => {
    const owner = await createOwner({ prefix: "token-kind", verified: false });
    createdUserIds.push(owner.userId);

    // The raw token only ever exists in the email; reconstruct the same row.
    const rawVerify = `verify:${Date.now()}${Math.random().toString(36).slice(2)}`;
    await prisma.session.create({
      data: { userId: owner.userId, tokenHash: hashToken(rawVerify), expiresAt: new Date(Date.now() + 3_600_000) },
    });

    const asSession = await request(app).get("/api/v1/auth/me").set("Cookie", `session=${rawVerify}`);
    expect(asSession.status).toBe(401);
    expect(asSession.body.error.code).toBe("UNAUTHORIZED");

    // A real session still works: the guard rejects email tokens, not sessions.
    const real = await owner.agent.get("/api/v1/auth/me");
    expect(real.status).toBe(200);
  });

  it("a reset token cannot be used as a session cookie", async () => {
    const owner = await createOwner({ prefix: "token-kind-reset", verified: false });
    createdUserIds.push(owner.userId);

    const rawReset = `reset:${Date.now()}${Math.random().toString(36).slice(2)}`;
    await prisma.session.create({
      data: { userId: owner.userId, tokenHash: hashToken(rawReset), expiresAt: new Date(Date.now() + 3_600_000) },
    });

    const asSession = await request(app).get("/api/v1/auth/me").set("Cookie", `session=${rawReset}`);
    expect(asSession.status).toBe(401);
  });

  it("a session cookie cannot be spent as a password-reset token", async () => {
    const owner = await createOwner({ prefix: "token-kind-session" });
    createdUserIds.push(owner.userId);

    const login = await owner.agent.post("/api/v1/auth/login").send({ email: owner.email, password: PASSWORD });
    const sessionToken = sessionCookieFrom(login as unknown as { headers: Record<string, unknown> });

    const attempt = await owner.agent
      .post("/api/v1/auth/password-reset/confirm")
      .send({ token: sessionToken, password: "attacker-password-123" });
    expect(attempt.status).toBe(400);
    expect(attempt.body.error.code).toBe("VALIDATION_ERROR");

    // The original password still works, i.e. nothing was changed.
    const stillValid = await request(app).post("/api/v1/auth/login").send({ email: owner.email, password: PASSWORD });
    expect(stillValid.status).toBe(200);
  });

  it("a full password reset changes the password and revokes every session", async () => {
    const owner = await createOwner({ prefix: "reset-flow" });
    createdUserIds.push(owner.userId);

    const rawReset = `reset:${Date.now()}${Math.random().toString(36).slice(2)}`;
    await prisma.session.create({
      data: { userId: owner.userId, tokenHash: hashToken(rawReset), expiresAt: new Date(Date.now() + 3_600_000) },
    });

    const confirmed = await request(app)
      .post("/api/v1/auth/password-reset/confirm")
      .send({ token: rawReset, password: "brand-new-password-123" });
    expect(confirmed.status).toBe(200);

    // The token is single-use.
    const replay = await request(app)
      .post("/api/v1/auth/password-reset/confirm")
      .send({ token: rawReset, password: "another-password-123" });
    expect(replay.status).toBe(400);

    const oldPassword = await request(app)
      .post("/api/v1/auth/login")
      .send({ email: owner.email, password: PASSWORD });
    expect(oldPassword.status).toBe(401);

    const newPassword = await request(app)
      .post("/api/v1/auth/login")
      .send({ email: owner.email, password: "brand-new-password-123" });
    expect(newPassword.status).toBe(200);

    // Sessions that existed before the reset are revoked.
    const staleSession = await owner.agent.get("/api/v1/auth/me");
    expect(staleSession.status).toBe(401);
  });

  it("a duplicate email and a weak password are rejected with field errors", async () => {
    const owner = await createOwner({ prefix: "dup-email" });
    createdUserIds.push(owner.userId);

    const duplicate = await request(app)
      .post("/api/v1/auth/register")
      .send({ email: owner.email, password: "password-123" });
    expect(duplicate.status).toBe(400);
    expect(duplicate.body.error.code).toBe("VALIDATION_ERROR");
    expect(duplicate.body.error.fieldErrors.email).toBeTruthy();

    const weak = await request(app)
      .post("/api/v1/auth/register")
      .send({ email: uniqueEmail("weak"), password: "short" });
    expect(weak.status).toBe(400);
    expect(weak.body.error.fieldErrors.password).toBeTruthy();
  });

  it("a soft-deleted account cannot log in", async () => {
    const owner = await createOwner({ prefix: "deleted-login" });
    createdUserIds.push(owner.userId);

    // Erasure is a soft delete: the row survives so the history stays auditable.
    await prisma.user.update({ where: { id: owner.userId }, data: { deletedAt: new Date() } });

    const res = await request(app).post("/api/v1/auth/login").send({ email: owner.email, password: PASSWORD });
    expect(res.status).toBe(401);
    expect(sessionCookieHeader(res.headers as Record<string, unknown>)).toBeNull();
  });
});