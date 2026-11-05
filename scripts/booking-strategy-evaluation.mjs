/**
 * Reproducible booking-race evaluation.
 *
 *   DATABASE_URL=... pnpm evaluate:booking
 *
 * The harness deliberately widens the race with a short pg_sleep after the
 * availability check. This measures the integrity behaviour of each strategy,
 * not the accidental timing of a fast local machine. It uses a disposable
 * database user/event and restores the exclusion constraint in finally.
 */
import fs from "node:fs";
import path from "node:path";
import { PrismaClient } from "../apps/api/node_modules/@prisma/client/default.js";

const prisma = new PrismaClient();
const TRIALS = Number(process.env.BOOKING_EVAL_TRIALS ?? 20);
const CONTENDERS = Number(process.env.BOOKING_EVAL_CONTENDERS ?? 32);
const SLEEP_MS = Number(process.env.BOOKING_EVAL_SLEEP_MS ?? 5);
const email = `booking-strategy-eval-${process.pid}@slotwise.test`;
const constraint = "bookings_no_host_overlap";
const sleepSql = `SELECT 1 AS slept FROM pg_sleep(${Math.max(0, SLEEP_MS) / 1000})`;

function percentile(values, p) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1)];
}

async function constraintExists() {
  const rows = await prisma.$queryRawUnsafe(
    "SELECT 1 FROM pg_constraint WHERE conname = $1",
    constraint,
  );
  return rows.length > 0;
}

async function dropConstraint() {
  await prisma.$executeRawUnsafe(`ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ${constraint}`);
}

async function addConstraint() {
  if (await constraintExists()) return;
  await prisma.$executeRawUnsafe(`
    ALTER TABLE bookings ADD CONSTRAINT ${constraint}
    EXCLUDE USING gist (user_id WITH =, tstzrange(start_at, end_at, '[)') WITH &&)
    WHERE (status = 'confirmed')
  `);
}

async function createFixture() {
  // Clean up abandoned fixtures from an interrupted local run before creating
  // the next one. The evaluation user is deliberately uniquely prefixed.
  await prisma.$executeRawUnsafe("DELETE FROM bookings WHERE user_id IN (SELECT id FROM users WHERE email LIKE 'booking-strategy-eval-%@slotwise.test')");
  await prisma.$executeRawUnsafe("DELETE FROM event_types WHERE user_id IN (SELECT id FROM users WHERE email LIKE 'booking-strategy-eval-%@slotwise.test')");
  await prisma.$executeRawUnsafe("DELETE FROM users WHERE email LIKE 'booking-strategy-eval-%@slotwise.test'");
  const user = await prisma.user.create({
    data: { email, passwordHash: "evaluation-only", emailVerifiedAt: new Date() },
  });
  const event = await prisma.eventType.create({
    data: {
      userId: user.id,
      title: "Booking strategy evaluation",
      slug: `booking-strategy-eval-${process.pid}`,
      durationMinutes: 30,
      timezone: "UTC",
      isPublished: true,
    },
  });
  return { userId: user.id, eventTypeId: event.id };
}

async function clearBookings(userId) {
  await prisma.booking.deleteMany({ where: { userId } });
}

function bookingData(fixture, index) {
  return {
    userId: fixture.userId,
    eventTypeId: fixture.eventTypeId,
    inviteeName: `Evaluation ${index}`,
    inviteeEmail: `evaluation-${index}@slotwise.test`,
    startAt: new Date("2035-01-02T10:00:00.000Z"),
    endAt: new Date("2035-01-02T10:30:00.000Z"),
    timezone: "UTC",
    status: "confirmed",
  };
}

async function checkThenInsert(fixture, index) {
  const existing = await prisma.booking.count({
    where: { userId: fixture.userId, status: "confirmed", startAt: { lt: new Date("2035-01-02T10:30:00Z") }, endAt: { gt: new Date("2035-01-02T10:00:00Z") } },
  });
  await prisma.$queryRawUnsafe(sleepSql);
  if (existing > 0) return false;
  await prisma.booking.create({ data: bookingData(fixture, index) });
  return true;
}

async function transactionalCheckWithoutConstraint(fixture, index) {
  return prisma.$transaction(async (tx) => {
    const existing = await tx.booking.count({
      where: { userId: fixture.userId, status: "confirmed", startAt: { lt: new Date("2035-01-02T10:30:00Z") }, endAt: { gt: new Date("2035-01-02T10:00:00Z") } },
    });
    await tx.$queryRawUnsafe(sleepSql);
    if (existing > 0) return false;
    await tx.booking.create({ data: bookingData(fixture, index) });
    return true;
  });
}

async function exclusionConstraint(fixture, index) {
  await prisma.booking.create({ data: bookingData(fixture, index) });
  return true;
}

async function runTrial(fixture, strategy) {
  const started = performance.now();
  const results = await Promise.all(
    Array.from({ length: CONTENDERS }, (_, index) => {
      const attemptStarted = performance.now();
      return strategy(fixture, index)
        .then((accepted) => ({ accepted, latencyMs: performance.now() - attemptStarted }))
        .catch((error) => ({ accepted: false, latencyMs: performance.now() - attemptStarted, error: String(error?.code ?? error?.message ?? error) }));
    }),
  );
  const confirmed = await prisma.booking.count({ where: { userId: fixture.userId, status: "confirmed" } });
  return {
    accepted: results.filter((result) => result.accepted).length,
    rejected: results.filter((result) => !result.accepted).length,
    errors: results.filter((result) => result.error).length,
    confirmed,
    violation: confirmed > 1,
    elapsedMs: performance.now() - started,
    p95AttemptMs: percentile(results.map((result) => result.latencyMs), 95),
    errorCodes: [...new Set(results.flatMap((result) => result.error ? [result.error] : []))],
  };
}

async function runStrategy(fixture, definition) {
  await clearBookings(fixture.userId);
  if (definition.constraint) await addConstraint();
  else await dropConstraint();
  const trials = [];
  for (let trial = 0; trial < TRIALS; trial += 1) {
    await clearBookings(fixture.userId);
    trials.push(await runTrial(fixture, definition.run));
  }
  return {
    id: definition.id,
    description: definition.description,
    trials,
    summary: {
      trials: trials.length,
      contendersPerTrial: CONTENDERS,
      violations: trials.filter((trial) => trial.violation).length,
      maxConfirmed: Math.max(...trials.map((trial) => trial.confirmed)),
      meanAccepted: trials.reduce((sum, trial) => sum + trial.accepted, 0) / trials.length,
      meanRejected: trials.reduce((sum, trial) => sum + trial.rejected, 0) / trials.length,
      meanP95AttemptMs: trials.reduce((sum, trial) => sum + trial.p95AttemptMs, 0) / trials.length,
    },
  };
}

function markdown(report) {
  const rows = report.strategies.map((strategy) => {
    const s = strategy.summary;
    return `| ${strategy.id} | ${s.trials} × ${s.contendersPerTrial} | ${s.meanAccepted.toFixed(1)} | ${s.meanRejected.toFixed(1)} | ${s.maxConfirmed} | ${s.violations}/${s.trials} | ${s.meanP95AttemptMs.toFixed(1)} ms |`;
  }).join("\n");
  return `# Booking strategy concurrency evaluation

Generated: ${report.generatedAt}

Profile: **${report.trials} trials × ${report.contenders} concurrent contenders**, same host and overlapping 30-minute slot each trial; race widening sleep: ${report.sleepMs} ms. Results are local PostgreSQL measurements, not production capacity claims.

| Strategy | Trials | Mean accepted | Mean rejected | Max confirmed | Violating trials | Mean p95 attempt |
|---|---:|---:|---:|---:|---:|---:|
${rows}

## Interpretation

- **check-then-insert** performs the availability check outside a transaction and is expected to admit overlapping rows under contention.
- **transactional-check-without-constraint** performs the check and insert in one default READ COMMITTED transaction, but without a database serialization or exclusion invariant; the check is still not a lock.
- **exclusion-constraint** relies on PostgreSQL's bookings_no_host_overlap GiST exclusion constraint. Concurrent losers are rejected and no trial may contain more than one confirmed row.

The application route uses the third strategy: it performs friendly pre-checks for UX, then the database constraint is the integrity authority. Re-run with BOOKING_EVAL_TRIALS, BOOKING_EVAL_CONTENDERS, and BOOKING_EVAL_SLEEP_MS to change the profile.
`;
}

const definitions = [
  { id: "check-then-insert", description: "Check and insert as separate operations; no constraint.", constraint: false, run: checkThenInsert },
  { id: "transactional-check-without-constraint", description: "Check and insert in one READ COMMITTED transaction; no constraint.", constraint: false, run: transactionalCheckWithoutConstraint },
  { id: "exclusion-constraint", description: "Concurrent insert protected by bookings_no_host_overlap.", constraint: true, run: exclusionConstraint },
];

let fixture;
try {
  fixture = await createFixture();
  const strategies = [];
  for (const definition of definitions) strategies.push(await runStrategy(fixture, definition));
  const report = {
    generatedAt: new Date().toISOString(),
    trials: TRIALS,
    contenders: CONTENDERS,
    sleepMs: SLEEP_MS,
    strategies,
  };
  const jsonPath = path.resolve("docs/booking-strategy-evaluation.json");
  const markdownPath = path.resolve("docs/BOOKING_STRATEGY_EVALUATION.md");
  fs.writeFileSync(jsonPath, `${JSON.stringify(report, null, 2)}\n`);
  fs.writeFileSync(markdownPath, markdown(report));
  console.log(markdown(report));
} finally {
  if (fixture) {
    await clearBookings(fixture.userId).catch(() => undefined);
    await prisma.user.delete({ where: { id: fixture.userId } }).catch(() => undefined);
  }
  await addConstraint().catch(() => undefined);
  await prisma.$disconnect();
}
