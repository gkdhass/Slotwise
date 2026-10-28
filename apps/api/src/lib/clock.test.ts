import { afterEach, describe, expect, it } from "vitest";
import { isFrozenForTesting, now, resetNowForTesting, setNowForTesting } from "./clock.js";

afterEach(() => {
  resetNowForTesting();
});

describe("clock", () => {
  it("follows real time when no override is set", () => {
    expect(isFrozenForTesting()).toBe(false);
    expect(Math.abs(now().getTime() - Date.now())).toBeLessThan(1000);
  });

  it("returns exactly the frozen instant", () => {
    setNowForTesting("2027-01-01T00:00:00.000Z");
    expect(isFrozenForTesting()).toBe(true);
    expect(now().toISOString()).toBe("2027-01-01T00:00:00.000Z");

    // Successive reads are stable: no drift even after a delay.
    const first = now().getTime();
    expect(now().getTime()).toBe(first);
  });

  it("hands out copies, so a caller cannot mutate the frozen instant", () => {
    setNowForTesting(new Date("2027-03-14T06:59:00.000Z"));
    const a = now();
    a.setFullYear(1999);
    expect(now().toISOString()).toBe("2027-03-14T06:59:00.000Z");
  });

  it("resumes real time after reset", () => {
    setNowForTesting(0);
    expect(now().getTime()).toBe(0);
    resetNowForTesting();
    expect(isFrozenForTesting()).toBe(false);
    expect(Math.abs(now().getTime() - Date.now())).toBeLessThan(1000);
  });

  it("rejects an invalid instant instead of silently freezing at Invalid Date", () => {
    expect(() => setNowForTesting("not-a-date")).toThrow(/Invalid clock instant/);
    expect(isFrozenForTesting()).toBe(false);
  });

  it("refuses to freeze when NODE_ENV=production", () => {
    const original = process.env.NODE_ENV;
    process.env.NODE_ENV = "production";
    try {
      expect(() => setNowForTesting("2027-01-01T00:00:00.000Z")).toThrow(/not available when NODE_ENV=production/);
      expect(isFrozenForTesting()).toBe(false);
    } finally {
      process.env.NODE_ENV = original;
    }
  });
});
