import { describe, it, expect, afterAll } from "vitest";
import { deleteHostAccount, deleteInviteeData } from "../../src/services/accountDeletion.js";
import {
  book,
  createEvent,
  createOwner,
  firstSlot,
  listSlots,
  prisma,
  purgeUsers,
  uniqueEmail,
} from "./helpers.js";

/**
 * NFR-04: the deletion path documented in docs/PRIVACY.md must actually work.
 * These tests exercise the same functions the operator script calls.
 */
const createdUserIds: string[] = [];

afterAll(async () => {
  await purgeUsers(createdUserIds);
  await prisma.$disconnect();
});

describe("account deletion", () => {
  it("removes the host, their events, availability, bookings, tokens, sessions and queued email", async () => {
    const owner = await createOwner({ prefix: "delete-host" });
    createdUserIds.push(owner.userId);
    const ev = await createEvent(owner.agent, { title: "Deletion target" });
    const slot = await firstSlot(ev.slug);
    const booked = await book(ev.slug, slot, { name: "Delete Me", email: uniqueEmail("delete-invitee") });
    expect(booked.status).toBe(201);

    const bookingId = booked.body.reference;
    expect(bookingId).toBeTruthy();
    expect(await prisma.managementToken.count({ where: { bookingId } })).toBeGreaterThan(0);
    expect(await prisma.outboxJob.count({ where: { bookingId } })).toBeGreaterThan(0);
    expect(await prisma.availabilityRule.count({ where: { eventTypeId: ev.id } })).toBeGreaterThan(0);

    const counts = await deleteHostAccount(owner.email);
    expect(counts).toMatchObject({ found: true, users: 1, eventTypes: 1, bookings: 1 });
    // register + login each create a session; both must be removed.
    expect(counts.sessions).toBeGreaterThanOrEqual(1);

    expect(await prisma.user.findUnique({ where: { id: owner.userId } })).toBeNull();
    expect(await prisma.eventType.count({ where: { userId: owner.userId } })).toBe(0);
    expect(await prisma.booking.count({ where: { userId: owner.userId } })).toBe(0);
    expect(await prisma.availabilityRule.count({ where: { eventTypeId: ev.id } })).toBe(0);
    expect(await prisma.managementToken.count({ where: { bookingId } })).toBe(0);
    expect(await prisma.outboxJob.count({ where: { bookingId } })).toBe(0);
    expect(await prisma.session.count({ where: { userId: owner.userId } })).toBe(0);
  });

  it("leaves another host's data untouched", async () => {
    const keeper = await createOwner({ prefix: "delete-keeper" });
    createdUserIds.push(keeper.userId);
    const keptEvent = await createEvent(keeper.agent, { title: "Keeper" });
    const keptSlot = await firstSlot(keptEvent.slug);
    expect((await book(keptEvent.slug, keptSlot, { name: "Kept Invitee" })).status).toBe(201);

    const doomed = await createOwner({ prefix: "delete-doomed" });
    createdUserIds.push(doomed.userId);
    await createEvent(doomed.agent, { title: "Doomed" });

    await deleteHostAccount(doomed.email);

    expect(await prisma.user.findUnique({ where: { id: keeper.userId } })).not.toBeNull();
    expect(await prisma.eventType.count({ where: { userId: keeper.userId } })).toBe(1);
    expect(await prisma.booking.count({ where: { userId: keeper.userId } })).toBe(1);
  });

  it("is idempotent and reports found:false for an unknown address", async () => {
    const owner = await createOwner({ prefix: "delete-twice" });
    createdUserIds.push(owner.userId);
    await createEvent(owner.agent, { title: "Twice" });

    expect((await deleteHostAccount(owner.email)).users).toBe(1);
    expect(await deleteHostAccount(owner.email)).toMatchObject({ found: false, users: 0 });
    expect(await deleteHostAccount("nobody-here@example.test")).toMatchObject({ found: false });
  });

  it("matches the address case-insensitively", async () => {
    const owner = await createOwner({ prefix: "delete-case" });
    createdUserIds.push(owner.userId);
    const counts = await deleteHostAccount(owner.email.toUpperCase());
    expect(counts).toMatchObject({ found: true, users: 1 });
  });

  it("dry run reports counts and deletes nothing", async () => {
    const owner = await createOwner({ prefix: "delete-dry" });
    createdUserIds.push(owner.userId);
    const ev = await createEvent(owner.agent, { title: "Dry run" });
    const slot = await firstSlot(ev.slug);
    await book(ev.slug, slot, { name: "Dry Invitee" });

    const preview = await deleteHostAccount(owner.email, { dryRun: true });
    expect(preview).toMatchObject({ found: true, eventTypes: 1, bookings: 1, users: 0 });
    expect(preview.outboxJobs).toBeGreaterThan(0);

    expect(await prisma.user.findUnique({ where: { id: owner.userId } })).not.toBeNull();
    expect(await prisma.booking.count({ where: { userId: owner.userId } })).toBe(1);
  });

  it("deletes one invitee's bookings across hosts without touching the hosts", async () => {
    const inviteeEmail = uniqueEmail("subject");
    const a = await createOwner({ prefix: "delete-subject-a" });
    const b = await createOwner({ prefix: "delete-subject-b" });
    createdUserIds.push(a.userId, b.userId);
    const evA = await createEvent(a.agent, { title: "Subject A" });
    const evB = await createEvent(b.agent, { title: "Subject B" });

    const slotsA = await listSlots(evA.slug);
    const slotsB = await listSlots(evB.slug);
    expect((await book(evA.slug, slotsA[0], { name: "Subject", email: inviteeEmail })).status).toBe(201);
    expect((await book(evB.slug, slotsB[0], { name: "Subject", email: inviteeEmail })).status).toBe(201);
    expect((await book(evB.slug, slotsB[1], { name: "Other", email: uniqueEmail("other") })).status).toBe(201);

    const counts = await deleteInviteeData(inviteeEmail.toUpperCase());
    expect(counts).toMatchObject({ found: true, bookings: 2, users: 0, eventTypes: 0 });

    expect(await prisma.booking.count({ where: { inviteeEmail: { equals: inviteeEmail, mode: "insensitive" } } })).toBe(0);
    expect(await prisma.user.findUnique({ where: { id: a.userId } })).not.toBeNull();
    expect(await prisma.eventType.count({ where: { userId: b.userId } })).toBe(1);
    // The other invitee's booking at host B survives.
    expect(await prisma.booking.count({ where: { userId: b.userId } })).toBe(1);
  });

  it("returns found:false for an invitee with no bookings", async () => {
    expect(await deleteInviteeData("never-booked@example.test")).toMatchObject({ found: false, bookings: 0 });
  });
});
