import { describe, it, expect, afterAll } from "vitest";
import { hashToken } from "../../src/lib/hash.js";
import {
  app,
  book,
  createEvent,
  createOwner,
  firstSlot,
  listSlots,
  prisma,
  purgeUsers,
  request,
  uniqueEmail,
} from "./helpers.js";

const createdUserIds: string[] = [];
const track = (id: string) => {
  createdUserIds.push(id);
  return id;
};

afterAll(async () => {
  await purgeUsers(createdUserIds);
  await prisma.$disconnect();
});

// ---------------------------------------------------------------------------
// F00 — Registration & first setup (S01 -> S02 -> S03 -> S04 -> S05)
// ---------------------------------------------------------------------------

describe("F00 registration and first setup", () => {
  it("F00-H1: register -> verify -> login -> create -> availability -> publish", async () => {
    const email = uniqueEmail("f00h1");
    const password = "password-123";
    const agent = request.agent(app);

    const reg = await agent.post("/api/v1/auth/register").send({ email, password });
    expect(reg.status).toBe(201);
    const user = await prisma.user.findUniqueOrThrow({ where: { email } });
    track(user.id);
    expect(user.emailVerifiedAt).toBeNull();

    // Simulate the emailed verification link (the raw token is only ever emailed).
    const rawToken = `verify:${Math.random().toString(36).slice(2)}${Date.now()}`;
    await prisma.session.create({
      data: { userId: user.id, tokenHash: hashToken(rawToken), expiresAt: new Date(Date.now() + 3_600_000) },
    });
    const verified = await agent.post("/api/v1/auth/verify-email").send({ token: rawToken });
    expect(verified.status).toBe(200);
    const afterVerify = await prisma.user.findUniqueOrThrow({ where: { id: user.id } });
    expect(afterVerify.emailVerifiedAt).not.toBeNull();

    const login = await agent.post("/api/v1/auth/login").send({ email, password });
    expect(login.status).toBe(200);

    const ev = await createEvent(agent, { title: "F00 session", durationMinutes: 45, timezone: "Asia/Kolkata" });
    expect(ev.slug).toBeTruthy();

    const me = await agent.get("/api/v1/auth/me");
    expect(me.status).toBe(200);
    expect(me.body.emailVerified).toBe(true);

    const pub = await request(app).get(`/api/v1/public/${ev.slug}`);
    expect(pub.status).toBe(200);
    expect(pub.body.title).toBe("F00 session");
    expect(pub.body.durationMinutes).toBe(45);
  });

  it("F00-E1: missing and malformed fields are rejected with field errors", async () => {
    const agent = request.agent(app);
    const missing = await agent.post("/api/v1/auth/register").send({});
    expect(missing.status).toBe(400);
    expect(missing.body.error.code).toBe("VALIDATION_ERROR");
    expect(Object.keys(missing.body.error.fieldErrors)).toEqual(expect.arrayContaining(["email", "password"]));

    const badEmail = await agent.post("/api/v1/auth/register").send({ email: "not-an-email", password: "password-123" });
    expect(badEmail.status).toBe(400);
    expect(badEmail.body.error.fieldErrors.email).toBeTruthy();

    const shortPassword = await agent.post("/api/v1/auth/register").send({ email: uniqueEmail("f00e1"), password: "short" });
    expect(shortPassword.status).toBe(400);
    expect(shortPassword.body.error.fieldErrors.password).toBeTruthy();
  });

  it("F00-N1: an unverified owner cannot publish", async () => {
    const { agent, userId } = await createOwner({ prefix: "f00n1", verified: false });
    track(userId);

    const created = await agent.post("/api/v1/event-types").send({
      title: "Unverified",
      durationMinutes: 30,
      timezone: "UTC",
    });
    expect(created.status).toBe(201);
    const rules = await agent
      .put(`/api/v1/event-types/${created.body.id}/availability`)
      .send([{ weekday: 1, startLocal: "09:00", endLocal: "17:00", timezone: "UTC" }]);
    expect(rules.status).toBe(200);

    const publish = await agent.patch(`/api/v1/event-types/${created.body.id}`).send({ isPublished: true });
    expect(publish.status).toBe(403);
    expect(publish.body.error.code).toBe("FORBIDDEN");

    const stored = await prisma.eventType.findUniqueOrThrow({ where: { id: created.body.id } });
    expect(stored.isPublished).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// F01 — Event management (S02 -> S03 -> S04 -> S05)
// ---------------------------------------------------------------------------

describe("F01 event management", () => {
  it("F01-H1: creating and publishing makes the event publicly bookable", async () => {
    const { agent, userId } = await createOwner({ prefix: "f01h1" });
    track(userId);
    const ev = await createEvent(agent, { title: "F01 published", durationMinutes: 60, timezone: "Europe/London" });

    const pub = await request(app).get(`/api/v1/public/${ev.slug}`);
    expect(pub.status).toBe(200);
    expect(pub.body).toMatchObject({
      title: "F01 published",
      durationMinutes: 60,
      timezone: "Europe/London",
    });

    const slots = await listSlots(ev.slug, { tz: "Europe/London", spanDays: 7 });
    expect(slots.length).toBeGreaterThan(0);
  });

  it("F01-E1: invalid duration and invalid availability ranges are rejected", async () => {
    const { agent, userId } = await createOwner({ prefix: "f01e1" });
    track(userId);

    const tooShort = await agent
      .post("/api/v1/event-types")
      .send({ title: "Too short", durationMinutes: 4, timezone: "UTC" });
    expect(tooShort.status).toBe(400);
    expect(tooShort.body.error.fieldErrors.durationMinutes).toBeTruthy();

    const tooLong = await agent
      .post("/api/v1/event-types")
      .send({ title: "Too long", durationMinutes: 481, timezone: "UTC" });
    expect(tooLong.status).toBe(400);

    const created = await agent.post("/api/v1/event-types").send({ title: "Ranges", durationMinutes: 30, timezone: "UTC" });
    expect(created.status).toBe(201);
    track(userId);

    const backwards = await agent
      .put(`/api/v1/event-types/${created.body.id}/availability`)
      .send([{ weekday: 1, startLocal: "17:00", endLocal: "09:00", timezone: "UTC" }]);
    expect(backwards.status).toBe(422);
    expect(backwards.body.error.code).toBe("UNPROCESSABLE");

    const overlapping = await agent.put(`/api/v1/event-types/${created.body.id}/availability`).send([
      { weekday: 1, startLocal: "09:00", endLocal: "12:00", timezone: "UTC" },
      { weekday: 1, startLocal: "11:00", endLocal: "13:00", timezone: "UTC" },
    ]);
    expect(overlapping.status).toBe(422);
    expect(overlapping.body.error.fieldErrors.availability).toBeTruthy();
  });

  it("F01-N1: another owner cannot read, edit or delete the event", async () => {
    const ownerA = await createOwner({ prefix: "f01n1a" });
    const ownerB = await createOwner({ prefix: "f01n1b" });
    track(ownerA.userId);
    track(ownerB.userId);
    const ev = await createEvent(ownerA.agent, { title: "Owner A only" });

    const read = await ownerB.agent.get(`/api/v1/event-types/${ev.id}`);
    expect(read.status).toBe(404);

    const patch = await ownerB.agent.patch(`/api/v1/event-types/${ev.id}`).send({ title: "Hijacked" });
    expect(patch.status).toBe(404);

    const del = await ownerB.agent.delete(`/api/v1/event-types/${ev.id}`);
    expect(del.status).toBe(404);

    const archive = await ownerB.agent.patch(`/api/v1/event-types/${ev.id}`).send({ isPublished: false });
    expect(archive.status).toBe(404);

    const stored = await prisma.eventType.findUniqueOrThrow({ where: { id: ev.id } });
    expect(stored.title).toBe("Owner A only");
    expect(stored.archivedAt).toBeNull();
    expect(stored.isPublished).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// F02 — Public booking (S06 -> S07 -> S08 -> S09)
// ---------------------------------------------------------------------------

describe("F02 public booking", () => {
  it("F02-H1: one booking creates a confirmed booking, a management token and an outbox job", async () => {
    const { agent, userId } = await createOwner({ prefix: "f02h1" });
    track(userId);
    const ev = await createEvent(agent, { title: "Bookable" });
    const slot = await firstSlot(ev.slug);

    const res = await book(ev.slug, slot, { name: "Ada", email: uniqueEmail("ada") });
    expect(res.status).toBe(201);
    expect(res.body.booking.status).toBe("confirmed");
    expect(res.body.managementToken).toMatch(/^[a-f0-9]{64}$/);

    const stored = await prisma.booking.findUniqueOrThrow({ where: { id: res.body.booking.id } });
    expect(stored.userId).toBe(userId);
    expect(stored.startAt.toISOString()).toBe(slot.startAt);

    const jobs = await prisma.outboxJob.findMany({ where: { bookingId: stored.id } });
    expect(jobs).toHaveLength(1);
    expect(jobs[0]).toMatchObject({ jobType: "booking_confirmation", status: "pending" });

    // The confirmation screen can load the booking with the management token.
    const manage = await request(app).get(`/api/v1/manage/${res.body.managementToken}`);
    expect(manage.status).toBe(200);
    expect(manage.body.id).toBe(stored.id);
    expect(manage.body.eventType.slug).toBe(ev.slug);

    // The slot disappears from the public list.
    const remaining = await listSlots(ev.slug, { spanDays: 21 });
    expect(remaining.some((s) => s.startAt === slot.startAt)).toBe(false);
  });

  it("F02-E1: a slot taken by someone else returns 409 SLOT_UNAVAILABLE", async () => {
    const { agent, userId } = await createOwner({ prefix: "f02e1" });
    track(userId);
    const ev = await createEvent(agent, { title: "Race" });
    const slot = await firstSlot(ev.slug);

    const first = await book(ev.slug, slot, { email: uniqueEmail("first") });
    expect(first.status).toBe(201);

    const second = await book(ev.slug, slot, { email: uniqueEmail("second") });
    expect(second.status).toBe(409);
    expect(second.body.error.code).toBe("SLOT_UNAVAILABLE");
    expect(second.body.error.message).toMatch(/no longer available/i);

    const count = await prisma.booking.count({ where: { userId, status: "confirmed" } });
    expect(count).toBe(1);
  });

  it("F02-N1: malformed, unpublished and invalid-slot bookings are rejected", async () => {
    const { agent, userId } = await createOwner({ prefix: "f02n1" });
    track(userId);
    const ev = await createEvent(agent, { title: "Validation" });
    const slot = await firstSlot(ev.slug);

    const badEmail = await book(ev.slug, slot, { email: "nope" });
    expect(badEmail.status).toBe(400);
    expect(badEmail.body.error.fieldErrors["invitee.email"]).toBeTruthy();

    const missingKey = await request(app).post(`/api/v1/public/${ev.slug}/bookings`).send({
      startAt: slot.startAt,
      timezone: "UTC",
      invitee: { name: "No Key", email: uniqueEmail("nokey") },
    });
    expect(missingKey.status).toBe(400);
    expect(missingKey.body.error.fieldErrors.idempotencyKey).toBeTruthy();

    const notASlot = await book(ev.slug, { startAt: new Date(new Date(slot.startAt).getTime() + 7 * 60_000).toISOString(), endAt: slot.endAt, label: "" });
    expect(notASlot.status).toBe(422);
    expect(notASlot.body.error.code).toBe("UNPROCESSABLE");

    const past = await book(ev.slug, { startAt: "2020-01-06T09:00:00.000Z", endAt: "2020-01-06T09:30:00.000Z", label: "" });
    expect(past.status).toBe(422);

    const draftOwner = await createOwner({ prefix: "f02n1draft" });
    track(draftOwner.userId);
    const draft = await createEvent(draftOwner.agent, { title: "Draft", publish: false });
    const draftSlot = await firstSlot(draft.slug).catch(() => null);
    const unpublished = await book(draft.slug, draftSlot ?? slot);
    expect(unpublished.status).toBe(404);
    expect(unpublished.body.error.code).toBe("NOT_FOUND");
  });

  it("F02-H2: retrying with the same idempotency key replays the same outcome", async () => {
    const { agent, userId } = await createOwner({ prefix: "f02h2" });
    track(userId);
    const ev = await createEvent(agent, { title: "Idempotent" });
    const slot = await firstSlot(ev.slug);
    const key = `idem-${Date.now()}`;
    const email = uniqueEmail("idem");

    const first = await book(ev.slug, slot, { idempotencyKey: key, email });
    expect(first.status).toBe(201);

    const retry = await book(ev.slug, slot, { idempotencyKey: key, email });
    expect(retry.status).toBe(200);
    expect(retry.body.reference).toBe(first.body.reference);
    expect(retry.body.replayed).toBe(true);
    expect(retry.body.managementToken).toBeNull();

    expect(await prisma.booking.count({ where: { userId: userId } })).toBe(1);
    const jobs = await prisma.outboxJob.count({ where: { booking: { userId: userId } } });
    expect(jobs).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// F03 — Management (cancel / reschedule)
// ---------------------------------------------------------------------------

describe("F03 management", () => {
  it("F03-H1: canceling releases the slot for a new booking", async () => {
    const { agent, userId } = await createOwner({ prefix: "f03h1" });
    track(userId);
    const ev = await createEvent(agent, { title: "Cancel me" });
    const slot = await firstSlot(ev.slug);
    const created = await book(ev.slug, slot);
    expect(created.status).toBe(201);
    const token = created.body.managementToken;

    const canceled = await request(app).post(`/api/v1/manage/${token}/cancel`);
    expect(canceled.status).toBe(200);
    expect(canceled.body.status).toBe("canceled");

    const jobs = await prisma.outboxJob.findMany({ where: { bookingId: created.body.booking.id } });
    expect(jobs.map((j) => j.jobType)).toEqual(expect.arrayContaining(["booking_confirmation", "booking_canceled"]));

    const slots = await listSlots(ev.slug, { spanDays: 21 });
    expect(slots.some((s) => s.startAt === slot.startAt)).toBe(true);

    const rebooked = await book(ev.slug, slot, { email: uniqueEmail("rebook") });
    expect(rebooked.status).toBe(201);
  });

  it("F03-E1: a reschedule into an occupied slot keeps the original booking unchanged", async () => {
    const { agent, userId } = await createOwner({ prefix: "f03e1" });
    track(userId);
    const ev = await createEvent(agent, { title: "Occupied destination" });
    const slots = await listSlots(ev.slug, { spanDays: 5 });
    expect(slots.length).toBeGreaterThanOrEqual(2);
    const first = slots[0];
    const second = slots[1];

    const bookingA = await book(ev.slug, first);
    const bookingB = await book(ev.slug, second);
    expect(bookingA.status).toBe(201);
    expect(bookingB.status).toBe(201);

    const reschedule = await request(app)
      .post(`/api/v1/manage/${bookingA.body.managementToken}/reschedule`)
      .send({ startAt: second.startAt, timezone: "UTC" });
    expect(reschedule.status).toBe(409);
    expect(reschedule.body.error.code).toBe("SLOT_UNAVAILABLE");

    const storedA = await prisma.booking.findUniqueOrThrow({ where: { id: bookingA.body.booking.id } });
    expect(storedA.startAt.toISOString()).toBe(first.startAt);
    expect(storedA.status).toBe("confirmed");

    const storedB = await prisma.booking.findUniqueOrThrow({ where: { id: bookingB.body.booking.id } });
    expect(storedB.startAt.toISOString()).toBe(second.startAt);
  });

  it("F03-N1: invalid and expired tokens reveal nothing", async () => {
    const { agent, userId } = await createOwner({ prefix: "f03n1" });
    track(userId);
    const ev = await createEvent(agent, { title: "Token" });
    const slot = await firstSlot(ev.slug);
    const created = await book(ev.slug, slot, { name: "Secret Person", email: uniqueEmail("secret") });
    expect(created.status).toBe(201);

    const unknown = "a".repeat(64);
    const unknownGet = await request(app).get(`/api/v1/manage/${unknown}`);
    const unknownCancel = await request(app).post(`/api/v1/manage/${unknown}/cancel`);
    expect(unknownGet.status).toBe(404);
    expect(unknownCancel.status).toBe(404);

    // Build a token row that is already expired.
    const expiredRaw = "b".repeat(64);
    await prisma.managementToken.create({
      data: {
        bookingId: created.body.booking.id,
        tokenHash: hashToken(expiredRaw),
        expiresAt: new Date(Date.now() - 60_000),
      },
    });
    const expiredGet = await request(app).get(`/api/v1/manage/${expiredRaw}`);
    const expiredReschedule = await request(app)
      .post(`/api/v1/manage/${expiredRaw}/reschedule`)
      .send({ startAt: slot.startAt, timezone: "UTC" });
    expect(expiredGet.status).toBe(404);
    expect(expiredReschedule.status).toBe(404);

    // Identical denial shape for every case (only the per-request id differs),
    // and no booking data leaked.
    expect(expiredGet.body.error.code).toBe(unknownGet.body.error.code);
    expect(expiredGet.body.error.message).toBe(unknownGet.body.error.message);
    expect(expiredGet.body.error.fieldErrors).toEqual(unknownGet.body.error.fieldErrors);
    expect(Object.keys(expiredGet.body)).toEqual(Object.keys(unknownGet.body));
    const serialized = JSON.stringify([unknownGet.body, expiredGet.body, unknownCancel.body]);
    expect(serialized).not.toContain("Secret Person");
    expect(serialized).not.toContain("inviteeName");
    expect(serialized).not.toContain(created.body.booking.id);
  });

  it("F03-H2: a successful reschedule moves the booking and frees the old slot", async () => {
    const { agent, userId } = await createOwner({ prefix: "f03h2" });
    track(userId);
    const ev = await createEvent(agent, { title: "Move me" });
    const slots = await listSlots(ev.slug, { spanDays: 5 });
    expect(slots.length).toBeGreaterThanOrEqual(3);
    const [oldSlot, newSlot] = slots;

    const created = await book(ev.slug, oldSlot);
    expect(created.status).toBe(201);
    const token = created.body.managementToken;

    const reschedule = await request(app)
      .post(`/api/v1/manage/${token}/reschedule`)
      .send({ startAt: newSlot.startAt, timezone: "UTC" });
    expect(reschedule.status).toBe(200);
    expect(new Date(reschedule.body.startAt).toISOString()).toBe(newSlot.startAt);

    const stored = await prisma.booking.findUniqueOrThrow({ where: { id: created.body.booking.id } });
    expect(stored.startAt.toISOString()).toBe(newSlot.startAt);
    expect(stored.status).toBe("confirmed");

    const jobs = await prisma.outboxJob.findMany({ where: { bookingId: stored.id } });
    expect(jobs.map((j) => j.jobType)).toEqual(expect.arrayContaining(["booking_rescheduled"]));

    const after = await listSlots(ev.slug, { spanDays: 5 });
    expect(after.some((s) => s.startAt === oldSlot.startAt)).toBe(true);
    expect(after.some((s) => s.startAt === newSlot.startAt)).toBe(false);
  });
});
