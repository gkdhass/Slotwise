import { describe, it, expect, afterAll, beforeEach, vi } from "vitest";

// The worker imports sendEmail directly, so the transport is mocked at module
// level. `emailBehaviour` lets each test decide what the transport does.
const emailBehaviour = {
  fail: false,
  calls: [] as Array<{ to: string; subject: string }>,
};

vi.mock("../../src/lib/email.js", () => ({
  sendEmail: vi.fn(async (msg: { to: string; subject: string }) => {
    emailBehaviour.calls.push({ to: msg.to, subject: msg.subject });
    if (emailBehaviour.fail) {
      const err = new Error("transport down");
      (err as Error & { code?: string }).code = "ETRANSPORT";
      throw err;
    }
  }),
}));

import { backoffMs, claimBatch, processJob, processOneBatch } from "../../src/worker/emailWorker.js";
import {
  app,
  book,
  createEvent,
  createOwner,
  firstSlot,
  prisma,
  purgeUsers,
  request,
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

beforeEach(async () => {
  emailBehaviour.fail = false;
  emailBehaviour.calls = [];
  vi.clearAllMocks();
  // The worker is global: neutralise jobs left behind by other suites so each
  // test only claims the job it created itself.
  await prisma.outboxJob.updateMany({
    where: { status: { in: ["pending", "processing"] } },
    data: { status: "sent" },
  });
});

async function makeBooking(prefix: string) {
  const owner = await createOwner({ prefix });
  track(owner.userId);
  const ev = await createEvent(owner.agent, { title: `${prefix} event` });
  const slot = await firstSlot(ev.slug);
  const created = await book(ev.slug, slot, { email: `${prefix}-invitee@example.test` });
  expect(created.status).toBe(201);
  // Registration sends its verification mail directly; discard that so the
  // counters below only reflect outbox deliveries.
  emailBehaviour.calls = [];
  return { owner, ev, slot, bookingId: created.body.booking.id as string };
}

describe("outbox worker", () => {
  it("rollback leaves no outbox job: a rejected booking writes nothing at all", async () => {
    const { ev, slot, owner } = await makeBooking("outbox-rollback");

    // The first booking already exists. Attempting the same slot again must
    // fail and must not leave a half-written booking or a second job behind.
    const before = await prisma.outboxJob.count({ where: { booking: { userId: owner.userId } } });
    expect(before).toBe(1);

    const failed = await book(ev.slug, slot, { email: "second@example.test" });
    expect(failed.status).toBe(409);
    expect(failed.body.error.code).toBe("SLOT_UNAVAILABLE");

    const after = await prisma.outboxJob.count({ where: { booking: { userId: owner.userId } } });
    expect(after).toBe(before);
    const bookings = await prisma.booking.count({ where: { userId: owner.userId } });
    expect(bookings).toBe(1);
  });

  it("sends a pending job, marks it sent, and does not resend it", async () => {
    const { bookingId } = await makeBooking("outbox-send");
    const jobs = await prisma.outboxJob.findMany({ where: { bookingId } });
    expect(jobs).toHaveLength(1);
    expect(jobs[0].status).toBe("pending");

    const claimed = await claimBatch(10);
    expect(claimed.map((j) => j.id)).toContain(jobs[0].id);
    // Claiming flips the row to `processing`, so a second claim cannot take it.
    const secondClaim = await claimBatch(10);
    expect(secondClaim.map((j) => j.id)).not.toContain(jobs[0].id);

    const target = claimed.find((j) => j.id === jobs[0].id)!;
    const sent = await processJob(target);
    expect(sent).toBe(true);
    expect(emailBehaviour.calls).toHaveLength(1);

    const stored = await prisma.outboxJob.findUniqueOrThrow({ where: { id: jobs[0].id } });
    expect(stored.status).toBe("sent");
    expect(stored.attempts).toBeGreaterThanOrEqual(1);
    expect(stored.processedAt).not.toBeNull();

    // Nothing left to claim, so nothing is sent again.
    const again = await processOneBatch();
    expect(again).toBe(0);
    expect(emailBehaviour.calls).toHaveLength(1);
  });

  it("retries with exponential backoff, then stops after the bounded attempt limit", async () => {
    const { bookingId } = await makeBooking("outbox-retry");
    const job = await prisma.outboxJob.findFirstOrThrow({ where: { bookingId } });
    emailBehaviour.fail = true;

    // Attempt 1..4: the job goes back to pending with a growing delay.
    const delays: number[] = [];
    for (let attempt = 1; attempt <= 4; attempt += 1) {
      // Make the job due again without waiting for the real backoff.
      await prisma.outboxJob.update({
        where: { id: job.id },
        data: { availableAt: new Date(Date.now() - 1000) },
      });
      const claimed = (await claimBatch(10)).find((j) => j.id === job.id);
      expect(claimed).toBeTruthy();
      const ok = await processJob(claimed!);
      expect(ok).toBe(false);

      const stored = await prisma.outboxJob.findUniqueOrThrow({ where: { id: job.id } });
      expect(stored.attempts).toBe(attempt);
      expect(stored.lastErrorCode).toBe("ETRANSPORT");
      if (attempt < 4) {
        expect(stored.status).toBe("pending");
        // availableAt is in the future and grows with each attempt.
        delays.push(stored.availableAt.getTime() - Date.now());
      }
    }
    expect(delays[1]).toBeGreaterThan(delays[0]);
    expect(delays[2]).toBeGreaterThan(delays[1]);
    expect(backoffMs(1)).toBeLessThan(backoffMs(2));
    expect(backoffMs(2)).toBeLessThan(backoffMs(3));

    // Final attempt (5 by default): the job is marked failed and is not retried.
    await prisma.outboxJob.update({
      where: { id: job.id },
      data: { availableAt: new Date(Date.now() - 1000) },
    });
    const lastClaim = (await claimBatch(10)).find((j) => j.id === job.id);
    expect(lastClaim).toBeTruthy();
    expect(await processJob(lastClaim!)).toBe(false);

    const failed = await prisma.outboxJob.findUniqueOrThrow({ where: { id: job.id } });
    expect(failed.status).toBe("failed");
    expect(failed.attempts).toBe(5);
    expect(failed.lastErrorCode).toBe("ETRANSPORT");

    // A failed job is never claimed again, even once it would be due.
    await prisma.outboxJob.update({ where: { id: job.id }, data: { availableAt: new Date(Date.now() - 60_000) } });
    expect((await claimBatch(50)).some((j) => j.id === job.id)).toBe(false);
    const handled = await processOneBatch();
    expect(handled).toBe(0);
    expect(emailBehaviour.calls).toHaveLength(5);
  });

  it("does not claim jobs that are not yet due", async () => {
    const { bookingId } = await makeBooking("outbox-notdue");
    const job = await prisma.outboxJob.findFirstOrThrow({ where: { bookingId } });
    await prisma.outboxJob.update({
      where: { id: job.id },
      data: { availableAt: new Date(Date.now() + 3_600_000) },
    });
    const claimed = await claimBatch(50);
    expect(claimed.some((j) => j.id === job.id)).toBe(false);
  });

  it("the worker HTTP endpoint is protected by the shared secret", async () => {
    const previous = process.env.WORKER_SECRET;
    process.env.WORKER_SECRET = "test-worker-secret";
    try {
      const unauth = await request(app).post("/api/v1/worker/run-outbox");
      expect(unauth.status).toBe(401);

      const wrong = await request(app).post("/api/v1/worker/run-outbox").set("x-worker-secret", "nope");
      expect(wrong.status).toBe(401);

      const ok = await request(app)
        .post("/api/v1/worker/run-outbox")
        .set("x-worker-secret", "test-worker-secret");
      expect(ok.status).toBe(200);
      expect(typeof ok.body.processed).toBe("number");
    } finally {
      if (previous === undefined) delete process.env.WORKER_SECRET;
      else process.env.WORKER_SECRET = previous;
    }
  });
});
