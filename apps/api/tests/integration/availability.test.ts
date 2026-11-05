import { describe, it, expect, afterAll } from "vitest";
import { createOwner, prisma, purgeUsers } from "./helpers.js";

/**
 * `PUT /event-types/:id/availability` replaces the whole rule set: delete every
 * row, insert the new ones. Commit eefd009 moved that pair into one interactive
 * transaction because a failure between the two used to leave a *published*
 * event with zero availability — every slot silently gone from its public page.
 *
 * These tests force a real insert failure (PostgreSQL rejects a NUL byte in a
 * text column, which the route's Zod/overlap checks do not look for) and assert
 * the previous rules survive. A delete-then-insert without a transaction would
 * leave the event empty here.
 */

const createdUserIds: string[] = [];
const track = (id: string) => {
  createdUserIds.push(id);
  return id;
};

afterAll(async () => {
  await purgeUsers(createdUserIds);
  await prisma.$disconnect();
});

type Rule = { weekday: number; startLocal: string; endLocal: string; timezone: string };

async function createEventWithRules(agent: Awaited<ReturnType<typeof createOwner>>["agent"], prefix: string) {
  const title = `Availability ${prefix}`;
  const created = await agent.post("/api/v1/event-types").send({ title, durationMinutes: 30, timezone: "UTC" });
  expect(created.status).toBe(201);
  const eventTypeId: string = created.body.id;

  const rules: Rule[] = [{ weekday: 1, startLocal: "09:00", endLocal: "17:00", timezone: "UTC" }];
  const saved = await agent.put(`/api/v1/event-types/${eventTypeId}/availability`).send(rules);
  expect(saved.status).toBe(200);
  expect(saved.body).toHaveLength(1);
  return { eventTypeId, rules };
}

describe("availability replacement is atomic", () => {
  it("a failing insert leaves the previous rules untouched", async () => {
    const { agent, userId } = await createOwner({ prefix: "avail-atomic" });
    track(userId);
    const { eventTypeId } = await createEventWithRules(agent, "atomic");

    const before = await prisma.availabilityRule.findMany({ where: { eventTypeId } });
    expect(before).toHaveLength(1);
    expect(before[0]).toMatchObject({ weekday: 1, startLocal: "09:00", endLocal: "17:00" });

    // Passes the route's own validation: valid HH:mm, end > start, no overlap,
    // timezone is a non-empty string. Fails only at the database, after the
    // transaction has already deleted the old rows.
    const failing: Rule[] = [
      { weekday: 2, startLocal: "10:00", endLocal: "11:00", timezone: "UTC" },
      { weekday: 3, startLocal: "10:00", endLocal: "11:00", timezone: "UTC\u0000" },
    ];
    const rejected = await agent.put(`/api/v1/event-types/${eventTypeId}/availability`).send(failing);
    expect(rejected.status).toBeGreaterThanOrEqual(400);

    const after = await prisma.availabilityRule.findMany({
      where: { eventTypeId },
      orderBy: { weekday: "asc" },
    });
    expect(after).toHaveLength(1);
    expect(after[0]).toMatchObject({ weekday: 1, startLocal: "09:00", endLocal: "17:00" });
  });

  it("a successful replacement applies both the delete and the insert", async () => {
    const { agent, userId } = await createOwner({ prefix: "avail-replace" });
    track(userId);
    const { eventTypeId } = await createEventWithRules(agent, "replace");

    const replacement: Rule[] = [
      { weekday: 4, startLocal: "08:00", endLocal: "12:00", timezone: "UTC" },
      { weekday: 5, startLocal: "13:00", endLocal: "18:00", timezone: "UTC" },
    ];
    const res = await agent.put(`/api/v1/event-types/${eventTypeId}/availability`).send(replacement);
    expect(res.status).toBe(200);
    expect(res.body).toHaveLength(2);

    const rows = await prisma.availabilityRule.findMany({
      where: { eventTypeId },
      orderBy: { weekday: "asc" },
    });
    expect(rows.map((r) => [r.weekday, r.startLocal, r.endLocal])).toEqual([
      [4, "08:00", "12:00"],
      [5, "13:00", "18:00"],
    ]);

    // The old Monday rule is gone: this is a replace, not a merge.
    expect(rows.some((r) => r.weekday === 1)).toBe(false);

    // The public event still reads availability from these rows.
    const detail = await agent.get(`/api/v1/event-types/${eventTypeId}`);
    expect(detail.status).toBe(200);
  });
});
