import { prisma } from "../lib/prisma.js";
import { sendEmail } from "../lib/email.js";

const MAX_ATTEMPTS = Number(process.env.OUTBOX_MAX_ATTEMPTS ?? 5);
const BASE_MS = Number(process.env.OUTBOX_BACKOFF_BASE_MS ?? 1000);

export async function processOneBatch(limit = 10): Promise<number> {
  const jobs: any[] = await prisma.$queryRaw`
    SELECT id, booking_id, job_type, payload, attempts
    FROM outbox_jobs
    WHERE status = 'pending' AND available_at <= now()
    ORDER BY available_at
    LIMIT ${limit}
    FOR UPDATE SKIP LOCKED
  `;
  let processed = 0;
  for (const job of jobs) {
    await prisma.outboxJob.update({ where: { id: job.id }, data: { status: "processing" } });
    try {
      const payload = job.payload as any;
      await sendEmail({
        to: payload?.to ?? "dev@example.test",
        subject: `Slotwise: ${job.job_type}`,
        text: JSON.stringify(payload),
        html: `<pre>${JSON.stringify(payload)}</pre>`,
      });
      await prisma.outboxJob.update({
        where: { id: job.id },
        data: { status: "sent", processedAt: new Date(), attempts: job.attempts + 1 },
      });
      processed++;
    } catch (err: any) {
      const attempts = job.attempts + 1;
      if (attempts >= MAX_ATTEMPTS) {
        await prisma.outboxJob.update({
          where: { id: job.id },
          data: { status: "failed", attempts, lastErrorCode: String(err?.message ?? "ERR"), availableAt: new Date() },
        });
      } else {
        const delay = BASE_MS * Math.pow(2, attempts);
        await prisma.outboxJob.update({
          where: { id: job.id },
          data: {
            status: "pending",
            attempts,
            lastErrorCode: String(err?.message ?? "ERR"),
            availableAt: new Date(Date.now() + delay),
          },
        });
      }
    }
  }
  return processed;
}

async function main() {
  console.log("email worker started");
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const n = await processOneBatch();
    if (n === 0) await new Promise((r) => setTimeout(r, 2000));
  }
}

if (process.env.NODE_ENV !== "test") {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}