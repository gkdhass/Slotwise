import "dotenv/config";
import { PrismaClient } from "@prisma/client";

/**
 * Verifies the single invariant the entire booking flow depends on:
 *
 *   bookings_no_host_overlap — EXCLUDE USING gist (user_id WITH =,
 *   tstzrange(start_at, end_at, '[)') WITH &&) WHERE (status = 'confirmed')
 *
 * Run against whatever DATABASE_URL is set (local or Neon). Exits non-zero if
 * the constraint is missing, half-configured, or does not actually reject
 * overlapping confirmed bookings with SQLSTATE 23P01.
 *
 * Deliberately uses Prisma only — no psql, no shelling out, no reading of the
 * connection string — so it behaves identically on any host.
 */

const prisma = new PrismaClient();
const tag = `verify-${Date.now().toString(36)}`;
let userId = null;

function fail(msg) {
  throw new Error(msg);
}

/** Prisma surfaces the SQLSTATE in the message; extract it reliably. */
function sqlStateOf(err) {
  const text = `${err?.message ?? ""}`;
  const m = text.match(/\b([0-9A-Z]{5})\b/);
  return m ? m[1] : null;
}

async function cleanup() {
  if (!userId) return;
  await prisma.booking.deleteMany({ where: { userId } });
  await prisma.eventType.deleteMany({ where: { userId } });
  await prisma.user.deleteMany({ where: { id: userId } });
  userId = null;
}

async function main() {
  console.log("1) constraint definition");
  const rows = await prisma.$queryRaw`
    SELECT c.conname AS name, pg_get_constraintdef(c.oid) AS def, c.contype AS type
    FROM pg_constraint c
    WHERE c.conname = 'bookings_no_host_overlap'
  `;

  if (rows.length !== 1) {
    fail(`expected exactly 1 constraint named bookings_no_host_overlap, found ${rows.length}`);
  }
  const { def, type } = rows[0];
  console.log(`   name: bookings_no_host_overlap`);
  console.log(`   type: ${type} (x = exclusion)`);
  console.log(`   definition: ${def}`);

  if (type !== "x") fail("constraint is not an exclusion constraint");
  if (!/EXCLUDE USING gist/i.test(def)) fail("constraint does not use EXCLUDE USING gist");
  if (!/user_id WITH =/i.test(def)) fail("constraint does not scope on user_id");
  if (!/tstzrange/i.test(def)) fail("constraint does not use tstzrange");
  if (!/WITH &&/.test(def)) fail("constraint does not use the && (overlap) operator");
  if (!/tstzrange\([^)]*'\[\)'/i.test(def)) fail("constraint range is not half-open [start, end)");
  if (!/WHERE\b/i.test(def) || !/confirmed/i.test(def)) {
    fail("constraint is not partial on status = 'confirmed'");
  }
  console.log("   -> shape is correct (gist + user_id + half-open tstzrange + && + partial on confirmed)");

  console.log("2) overlapping confirmed bookings must fail with 23P01");
  const user = await prisma.user.create({
    data: {
      email: `${tag}@verify.invalid`,
      passwordHash: "not-a-real-hash",
      role: "owner",
      emailVerifiedAt: new Date(),
    },
  });
  userId = user.id;

  const eventType = await prisma.eventType.create({
    data: {
      userId: user.id,
      title: "Constraint probe",
      slug: `${tag}-probe`,
      durationMinutes: 30,
      timezone: "UTC",
      isPublished: false,
    },
  });

  // Anchor in the far future so the probe never collides with real data.
  const base = Date.UTC(2099, 0, 4, 10, 0, 0);
  const first = new Date(base);
  const firstEnd = new Date(base + 30 * 60_000);
  const overlapping = new Date(base + 15 * 60_000);
  const overlappingEnd = new Date(base + 45 * 60_000);
  const adjacent = new Date(base + 30 * 60_000);
  const adjacentEnd = new Date(base + 60 * 60_000);

  await prisma.booking.create({
    data: {
      userId: user.id,
      eventTypeId: eventType.id,
      inviteeName: "Probe A",
      inviteeEmail: `${tag}-a@verify.invalid`,
      startAt: first,
      endAt: firstEnd,
      timezone: "UTC",
      status: "confirmed",
    },
  });
  console.log("   first booking inserted");

  let rejected = false;
  let state = null;
  try {
    await prisma.booking.create({
      data: {
        userId: user.id,
        eventTypeId: eventType.id,
        inviteeName: "Probe B",
        inviteeEmail: `${tag}-b@verify.invalid`,
        startAt: overlapping,
        endAt: overlappingEnd,
        timezone: "UTC",
        status: "confirmed",
      },
    });
  } catch (err) {
    rejected = true;
    state = sqlStateOf(err);
  }

  if (!rejected) fail("overlapping booking was ACCEPTED — the exclusion constraint is not enforced");
  if (state !== "23P01") fail(`overlap was rejected but SQLSTATE was ${state}, expected 23P01`);
  console.log(`   overlapping insert rejected with SQLSTATE ${state}`);

  const stillOne = await prisma.booking.count({ where: { userId: user.id, status: "confirmed" } });
  if (stillOne !== 1) fail(`expected 1 confirmed booking after the rejection, found ${stillOne}`);
  console.log("   no partial row was written (still exactly 1 confirmed booking)");

  console.log("3) adjacent [start, end) boundaries must still be allowed");
  const adjacentBooking = await prisma.booking.create({
    data: {
      userId: user.id,
      eventTypeId: eventType.id,
      inviteeName: "Probe C",
      inviteeEmail: `${tag}-c@verify.invalid`,
      startAt: adjacent,
      endAt: adjacentEnd,
      timezone: "UTC",
      status: "confirmed",
    },
  });
  console.log(`   back-to-back booking accepted (${adjacentBooking.id})`);

  console.log("4) cancelled bookings must not block the slot");
  await prisma.booking.update({
    where: { id: adjacentBooking.id },
    data: { status: "canceled" },
  });
  await prisma.booking.create({
    data: {
      userId: user.id,
      eventTypeId: eventType.id,
      inviteeName: "Probe D",
      inviteeEmail: `${tag}-d@verify.invalid`,
      startAt: adjacent,
      endAt: adjacentEnd,
      timezone: "UTC",
      status: "confirmed",
    },
  });
  console.log("   re-booked the same slot after cancelling the previous booking");

  const version = await prisma.$queryRaw`SELECT version() AS v`;
  console.log(`5) server: ${version[0].v}`);
}

main()
  .then(async () => {
    await cleanup();
    console.log("\nRESULT: PASS — exclusion constraint verified");
    await prisma.$disconnect();
  })
  .catch(async (err) => {
    console.log(`\nRESULT: FAIL — ${err.message}`);
    try {
      await cleanup();
    } catch {
      /* best effort */
    }
    await prisma.$disconnect();
    process.exit(1);
  });
