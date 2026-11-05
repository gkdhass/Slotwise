import "dotenv/config";
import { prisma } from "../lib/prisma.js";
import { sendEmail } from "../lib/email.js";

const MAX_ATTEMPTS = Number(process.env.OUTBOX_MAX_ATTEMPTS ?? 5);
const BASE_MS = Number(process.env.OUTBOX_BACKOFF_BASE_MS ?? 1000);
const BACKOFF_CAP_MS = Number(process.env.OUTBOX_BACKOFF_CAP_MS ?? 60_000);

export type ClaimedJob = {
  id: string;
  bookingId: string | null;
  jobType: string;
  payload: unknown;
  attempts: number;
};

/**
 * Claims up to `limit` due jobs inside a short transaction using
 * FOR UPDATE SKIP LOCKED, so concurrent workers never take the same job.
 * The row is marked `processing` before the transaction commits; the network
 * call happens after commit and can therefore never hold a row lock.
 */
export async function claimBatch(limit = 10): Promise<ClaimedJob[]> {
  const claimed = await prisma.$transaction(async (tx) => {
    const rows = await tx.$queryRaw<Array<{ id: string }>>`
      SELECT id FROM outbox_jobs
      WHERE status = 'pending' AND available_at <= now()
      ORDER BY available_at
      LIMIT ${limit}
      FOR UPDATE SKIP LOCKED
    `;
    if (rows.length === 0) return [];
    const ids = rows.map((r) => r.id);
    await tx.outboxJob.updateMany({ where: { id: { in: ids } }, data: { status: "processing" } });
    const jobs = await tx.outboxJob.findMany({ where: { id: { in: ids } }, orderBy: { availableAt: "asc" } });
    return jobs.map((j) => ({
      id: j.id,
      bookingId: j.bookingId,
      jobType: j.jobType,
      payload: j.payload,
      attempts: j.attempts,
    }));
  });
  return claimed;
}

export function backoffMs(attempts: number): number {
  return Math.min(BASE_MS * Math.pow(2, Math.max(0, attempts - 1)), BACKOFF_CAP_MS);
}

/** Processes a single claimed job. Returns true when the job was sent. */
export async function processJob(job: ClaimedJob): Promise<boolean> {
  const payload = (job.payload ?? {}) as { to?: string };
  const attempts = job.attempts + 1;
  try {
    await sendEmail({
      to: payload.to ?? "dev@example.test",
      subject: `Slotwise: ${job.jobType}`,
      text: JSON.stringify(job.payload),
      html: `<pre>${JSON.stringify(job.payload)}</pre>`,
    });
    await prisma.outboxJob.update({
      where: { id: job.id },
      data: { status: "sent", processedAt: new Date(), attempts, lastErrorCode: null },
    });
    return true;
  } catch (err: any) {
    const errorCode = String(err?.code ?? err?.name ?? "ERR").slice(0, 64);
    if (attempts >= MAX_ATTEMPTS) {
      await prisma.outboxJob.update({
        where: { id: job.id },
        data: { status: "failed", attempts, lastErrorCode: errorCode },
      });
    } else {
      await prisma.outboxJob.update({
        where: { id: job.id },
        data: {
          status: "pending",
          attempts,
          lastErrorCode: errorCode,
          availableAt: new Date(Date.now() + backoffMs(attempts)),
        },
      });
    }
    return false;
  }
}

export async function processOneBatch(limit = 10): Promise<number> {
  const jobs = await claimBatch(limit);
  let sent = 0;
  for (const job of jobs) {
    if (await processJob(job)) sent += 1;
  }
  return sent;
}

async function main() {
  console.log("outbox worker started");
  for (;;) {
    const n = await processOneBatch();
    if (n === 0) await new Promise((r) => setTimeout(r, 2000));
  }
}

if (process.env.NODE_ENV !== "test" && process.env.WORKER_STANDALONE !== "false") {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
