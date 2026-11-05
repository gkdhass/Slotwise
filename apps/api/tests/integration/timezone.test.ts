import { describe, it, expect, afterAll, beforeAll } from "vitest";
import { resetNowForTesting, setNowForTesting } from "../../src/lib/clock.js";
import {
  app,
  book,
  createEvent,
  createOwner,
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

/**
 * The assertions below name exact DST dates, so the server clock is frozen just
 * before them. Without this the suite rots: `generateSlots` hides slots that
 * start in the past, so once real time passes March/June/November 2027 every
 * window below would come back empty.
 */
const PINNED_NOW = "2027-01-01T00:00:00.000Z";

beforeAll(() => {
  setNowForTesting(PINNED_NOW);
});

afterAll(async () => {
  resetNowForTesting();
  await purgeUsers(createdUserIds);
  await prisma.$disconnect();
});

type Slot = { startAt: string; endAt: string; label: string };

/** Raw slots query with an explicit UTC window. */
async function slotsBetween(slug: string, fromIso: string, toIso: string, tz: string): Promise<Slot[]> {
  const res = await request(app)
    .get(`/api/v1/public/${slug}/slots`)
    .query({ from: fromIso, to: toIso, tz });
  if (res.status !== 200) throw new Error(`slots ${res.status}: ${JSON.stringify(res.body)}`);
  return res.body as Slot[];
}

/** Parses the API label format "EEE d MMM, h:mm a" into minutes past midnight. */
function labelMinutes(label: string): number {
  const m = label.match(/(\d{1,2}):(\d{2})\s*(am|pm)/i);
  if (!m) throw new Error(`unparseable label: ${label}`);
  let hour = Number(m[1]) % 12;
  if (m[3].toLowerCase() === "pm") hour += 12;
  return hour * 60 + Number(m[2]);
}

// --- DST boundaries in America/New_York (2027) -----------------------------
// Spring forward: Sunday 14 March 2027, 02:00 -> 03:00.
// Fall back:      Sunday  7 November 2027, 02:00 -> 01:00.
const SPRING_DAY = { from: "2027-03-14T00:00:00.000Z", to: "2027-03-15T00:00:00.000Z" };
const FALL_DAY = { from: "2027-11-07T00:00:00.000Z", to: "2027-11-08T00:00:00.000Z" };

const ALL_DAYS = [0, 1, 2, 3, 4, 5, 6];

describe("time zones at the API level", () => {
  it("DST spring forward skips the missing hour (no 02:00 slot on the transition day)", async () => {
    const { agent, userId } = await createOwner({ prefix: "tz-spring" });
    track(userId);
    const ev = await createEvent(agent, {
      title: "Spring forward",
      durationMinutes: 30,
      timezone: "America/New_York",
      rules: ALL_DAYS.map((weekday) => ({ weekday, startLocal: "00:00", endLocal: "04:00" })),
    });

    const slots = await slotsBetween(ev.slug, SPRING_DAY.from, SPRING_DAY.to, "America/New_York");
    // 00:00-04:00 wall clock, but 02:00-03:00 does not exist => 3h => 6 slots.
    expect(slots).toHaveLength(6);
    for (const s of slots) {
      expect(s.label).not.toMatch(/\b2:00\s*am/i);
      expect(s.label).not.toMatch(/\b2:30\s*am/i);
    }
    // The wall clock jumps 01:30 -> 03:00 while UTC advances only 30 minutes.
    const labels = slots.map((s) => labelMinutes(s.label));
    expect(labels).toEqual([0, 30, 60, 90, 180, 210]);
    expect(new Date(slots[4].startAt).getTime() - new Date(slots[3].startAt).getTime()).toBe(30 * 60_000);

    // Every slot is half an hour long and strictly increasing.
    for (const s of slots) {
      expect(new Date(s.endAt).getTime() - new Date(s.startAt).getTime()).toBe(30 * 60_000);
    }
  });

  it("DST fall back repeats the 01:00 hour (10 slots, two distinct instants at 1:00 am)", async () => {
    const { agent, userId } = await createOwner({ prefix: "tz-fall" });
    track(userId);
    const ev = await createEvent(agent, {
      title: "Fall back",
      durationMinutes: 30,
      timezone: "America/New_York",
      rules: ALL_DAYS.map((weekday) => ({ weekday, startLocal: "00:00", endLocal: "04:00" })),
    });

    const slots = await slotsBetween(ev.slug, FALL_DAY.from, FALL_DAY.to, "America/New_York");
    // 00:00-04:00 wall clock with 02:00-03:00 occurring twice => 5h => 10 slots.
    expect(slots).toHaveLength(10);

    const oneAm = slots.filter((s) => labelMinutes(s.label) === 60);
    expect(oneAm).toHaveLength(2);
    // Same wall-clock label, different UTC instants: this is the repeat, not a duplicate.
    expect(oneAm[0].label).toBe(oneAm[1].label);
    expect(oneAm[0].startAt).not.toBe(oneAm[1].startAt);
    expect(new Date(oneAm[1].startAt).getTime() - new Date(oneAm[0].startAt).getTime()).toBe(60 * 60_000);

    // The set of slot instants is unique: no slot is emitted twice.
    const unique = new Set(slots.map((s) => s.startAt));
    expect(unique.size).toBe(slots.length);
  });

  it("host in Asia/Kolkata and invitee in America/New_York see the same instants with different labels", async () => {
    const { agent, userId } = await createOwner({ prefix: "tz-cross" });
    track(userId);
    const ev = await createEvent(agent, {
      title: "Cross zone",
      durationMinutes: 30,
      timezone: "Asia/Kolkata",
      rules: ALL_DAYS.map((weekday) => ({ weekday, startLocal: "09:00", endLocal: "17:00" })),
    });

    const from = "2027-06-07T00:00:00.000Z";
    const to = "2027-06-09T00:00:00.000Z";
    const hostSlots = await slotsBetween(ev.slug, from, to, "Asia/Kolkata");
    const inviteeSlots = await slotsBetween(ev.slug, from, to, "America/New_York");

    expect(hostSlots.length).toBeGreaterThan(0);
    // Availability is stored in the host zone, so both views offer the same instants.
    expect(inviteeSlots.map((s) => s.startAt)).toEqual(hostSlots.map((s) => s.startAt));

    // New York is 9.5 hours behind Kolkata: same instant, different wall clock.
    for (let i = 0; i < hostSlots.length; i += 1) {
      const host = labelMinutes(hostSlots[i].label);
      const invitee = labelMinutes(inviteeSlots[i].label);
      const delta = (host - invitee + 24 * 60) % (24 * 60);
      expect(delta).toBe(9 * 60 + 30);
    }
    expect(hostSlots[0].label).not.toBe(inviteeSlots[0].label);
    // Host slots read as business hours; the invitee sees some of them late at night.
    expect(hostSlots.some((s) => labelMinutes(s.label) >= 9 * 60 && labelMinutes(s.label) < 17 * 60)).toBe(true);
  });

  it("a booking stores the invitee's time zone and keeps the same instant", async () => {
    const { agent, userId } = await createOwner({ prefix: "tz-book" });
    track(userId);
    const ev = await createEvent(agent, {
      title: "Zone booking",
      durationMinutes: 30,
      timezone: "Asia/Kolkata",
      rules: ALL_DAYS.map((weekday) => ({ weekday, startLocal: "09:00", endLocal: "17:00" })),
    });

    const slots = await slotsBetween(ev.slug, "2027-06-07T00:00:00.000Z", "2027-06-09T00:00:00.000Z", "America/New_York");
    const target = slots[0];

    const res = await book(ev.slug, target, {
      email: uniqueEmail("tz-book"),
      tz: "America/New_York",
      name: "Zone Invitee",
    });
    expect(res.status).toBe(201);
    expect(new Date(res.body.booking.startAt).toISOString()).toBe(target.startAt);
    expect(res.body.booking.timezone).toBe("America/New_York");

    // The management view keeps the invitee's zone so a later reschedule stays consistent.
    const manage = await request(app).get(`/api/v1/manage/${res.body.managementToken}`);
    expect(manage.status).toBe(200);
    expect(new Date(manage.body.startAt).toISOString()).toBe(target.startAt);
    expect(manage.body.timezone).toBe("America/New_York");
    expect(manage.body.eventType.timezone).toBe("Asia/Kolkata");

    // The slot is gone from both zone views.
    const afterNy = await slotsBetween(ev.slug, "2027-06-07T00:00:00.000Z", "2027-06-09T00:00:00.000Z", "America/New_York");
    const afterKol = await slotsBetween(ev.slug, "2027-06-07T00:00:00.000Z", "2027-06-09T00:00:00.000Z", "Asia/Kolkata");
    expect(afterNy.some((s) => s.startAt === target.startAt)).toBe(false);
    expect(afterKol.some((s) => s.startAt === target.startAt)).toBe(false);
  });

  it("an unknown or malformed time zone is rejected with 422 on slots and booking", async () => {
    const { agent, userId } = await createOwner({ prefix: "tz-bad" });
    track(userId);
    const ev = await createEvent(agent, { title: "Bad zone" });

    const slots = await request(app)
      .get(`/api/v1/public/${ev.slug}/slots`)
      .query({ from: "2027-06-07T00:00:00.000Z", to: "2027-06-08T00:00:00.000Z", tz: "Mars/Olympus" });
    expect(slots.status).toBe(422);
    expect(slots.body.error.code).toBe("UNPROCESSABLE");
    expect(slots.body.error.fieldErrors.tz).toBeTruthy();

    const booking = await request(app).post(`/api/v1/public/${ev.slug}/bookings`).send({
      startAt: "2027-06-07T09:00:00.000Z",
      timezone: "Mars/Olympus",
      invitee: { name: "Nobody", email: uniqueEmail("badzone") },
      idempotencyKey: `badzone-${Date.now()}`,
    });
    expect(booking.status).toBe(422);
    expect(booking.body.error.fieldErrors.timezone).toBeTruthy();
  });

  it("hides slots that start before the injected clock (clock is wired into the route)", async () => {
    const { agent, userId } = await createOwner({ prefix: "tz-clock" });
    track(userId);
    const ev = await createEvent(agent, {
      title: "Clock wiring",
      durationMinutes: 30,
      timezone: "America/New_York",
      rules: ALL_DAYS.map((weekday) => ({ weekday, startLocal: "09:00", endLocal: "12:00" })),
    });

    // Monday 7 June 2027, EDT (UTC-4): 09:00-12:00 wall clock == 13:00-16:00 UTC.
    const from = "2027-06-07T00:00:00.000Z";
    const to = "2027-06-08T00:00:00.000Z";

    // Pinned at 2027-01-01 (before the window): the whole grid is in the future.
    const future = await slotsBetween(ev.slug, from, to, "America/New_York");
    expect(future.map((s) => s.startAt)).toEqual([
      "2027-06-07T13:00:00.000Z",
      "2027-06-07T13:30:00.000Z",
      "2027-06-07T14:00:00.000Z",
      "2027-06-07T14:30:00.000Z",
      "2027-06-07T15:00:00.000Z",
      "2027-06-07T15:30:00.000Z",
    ]);

    // Move the clock into the middle of that grid: slots starting before it
    // (with a one-minute grace) must disappear, later ones must remain.
    setNowForTesting("2027-06-07T14:10:00.000Z");
    try {
      const remaining = await slotsBetween(ev.slug, from, to, "America/New_York");
      expect(remaining.map((s) => s.startAt)).toEqual([
        "2027-06-07T14:30:00.000Z",
        "2027-06-07T15:00:00.000Z",
        "2027-06-07T15:30:00.000Z",
      ]);
    } finally {
      setNowForTesting(PINNED_NOW);
    }

    // Restoring the clock restores the full grid.
    const restored = await slotsBetween(ev.slug, from, to, "America/New_York");
    expect(restored).toHaveLength(6);
  });

  it("an inverted or overlong slot window is rejected instead of returning garbage", async () => {
    const { agent, userId } = await createOwner({ prefix: "tz-window" });
    track(userId);
    const ev = await createEvent(agent, { title: "Window" });

    const inverted = await request(app)
      .get(`/api/v1/public/${ev.slug}/slots`)
      .query({ from: "2027-06-09T00:00:00.000Z", to: "2027-06-07T00:00:00.000Z", tz: "UTC" });
    expect(inverted.status).toBe(422);

    const tooLong = await request(app)
      .get(`/api/v1/public/${ev.slug}/slots`)
      .query({ from: "2027-06-07T00:00:00.000Z", to: "2027-12-07T00:00:00.000Z", tz: "UTC" });
    expect(tooLong.status).toBe(422);
    expect(tooLong.body.error.message).toMatch(/31 days/i);
    expect(tooLong.body.error.fieldErrors.to).toBeTruthy();
  });
});
