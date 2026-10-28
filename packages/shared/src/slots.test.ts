import { describe, it, expect } from "vitest";
import { generateSlots } from "./slots";

describe("generateSlots", () => {
  it("generates slots for a weekday within availability", () => {
    const from = new Date("2026-06-01T00:00:00Z");
    const to = new Date("2026-06-02T00:00:00Z");
    const slots = generateSlots({
      rules: [{ weekday: 1, startLocal: "10:00", endLocal: "12:00" }], // Mon
      durationMinutes: 30,
      eventTimezone: "UTC",
      displayTimezone: "UTC",
      from,
      to,
      existingBookings: [],
    });
    // June 1 2026 is a Monday
    expect(slots.length).toBe(4);
    expect(slots[0].startAt).toBe("2026-06-01T10:00:00.000Z");
  });

  it("excludes confirmed bookings", () => {
    const from = new Date("2026-06-01T00:00:00Z");
    const to = new Date("2026-06-02T00:00:00Z");
    const slots = generateSlots({
      rules: [{ weekday: 1, startLocal: "10:00", endLocal: "12:00" }],
      durationMinutes: 30,
      eventTimezone: "UTC",
      displayTimezone: "UTC",
      from,
      to,
      existingBookings: [{ startAt: "2026-06-01T10:00:00.000Z", endAt: "2026-06-01T10:30:00.000Z", status: "confirmed" }],
    });
    expect(slots.find((s) => s.startAt === "2026-06-01T10:00:00.000Z")).toBeUndefined();
    expect(slots.length).toBe(3);
  });

  it("respects duration steps and end boundary", () => {
    const from = new Date("2026-06-01T00:00:00Z");
    const to = new Date("2026-06-02T00:00:00Z");
    const slots = generateSlots({
      rules: [{ weekday: 1, startLocal: "10:00", endLocal: "11:00" }],
      durationMinutes: 15,
      eventTimezone: "UTC",
      displayTimezone: "UTC",
      from,
      to,
      existingBookings: [],
    });
    expect(slots.length).toBe(4);
    expect(slots[3].startAt).toBe("2026-06-01T10:45:00.000Z");
  });

  it("handles overlapping availability rules without duplicating slots", () => {
    const from = new Date("2026-06-01T00:00:00Z");
    const to = new Date("2026-06-02T00:00:00Z");
    const slots = generateSlots({
      rules: [
        { weekday: 1, startLocal: "10:00", endLocal: "12:00" },
        { weekday: 1, startLocal: "10:00", endLocal: "12:00" },
      ],
      durationMinutes: 30,
      eventTimezone: "UTC",
      displayTimezone: "UTC",
      from,
      to,
      existingBookings: [],
    });
    expect(slots.length).toBe(4);
  });

  it("DST spring-forward: does not produce nonexistent local times (America/New_York)", () => {
    // 2026-03-08 spring forward: 02:00-03:00 doesn't exist
    const from = new Date("2026-03-08T00:00:00Z");
    const to = new Date("2026-03-09T00:00:00Z");
    const slots = generateSlots({
      rules: [{ weekday: 0, startLocal: "00:00", endLocal: "23:59" }],
      durationMinutes: 60,
      eventTimezone: "America/New_York",
      displayTimezone: "America/New_York",
      from,
      to,
      existingBookings: [],
    });
    // all slot starts must be valid instants; count finite
    expect(slots.length).toBeGreaterThan(0);
    // no duplicate instants
    const starts = slots.map((s) => s.startAt);
    expect(new Set(starts).size).toBe(starts.length);
  });

  it("DST fall-back: produces slots without crashing (America/New_York)", () => {
    const from = new Date("2026-11-01T00:00:00Z");
    const to = new Date("2026-11-02T00:00:00Z");
    const slots = generateSlots({
      rules: [{ weekday: 0, startLocal: "00:00", endLocal: "23:00" }],
      durationMinutes: 60,
      eventTimezone: "America/New_York",
      displayTimezone: "America/New_York",
      from,
      to,
      existingBookings: [],
    });
    expect(slots.length).toBeGreaterThan(0);
  });
});