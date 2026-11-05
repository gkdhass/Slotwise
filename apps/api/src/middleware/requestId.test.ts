import { describe, expect, it } from "vitest";
import request from "supertest";
import app from "../index.js";
import { normaliseRequestId } from "./requestId.js";

describe("request id", () => {
  it("echoes a well-formed incoming id in the response header", async () => {
    const res = await request(app).get("/health").set("x-request-id", "abc-123-XYZ_9");
    expect(res.headers["x-request-id"]).toBe("abc-123-XYZ_9");
  });

  it("generates an id when the header is absent", async () => {
    const res = await request(app).get("/health");
    expect(res.headers["x-request-id"]).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("replaces a malformed id instead of reflecting it", () => {
    for (const bad of ["short", "has space", "line\nbreak", "<script>", "x".repeat(200), ""]) {
      const id = normaliseRequestId(bad);
      expect(id).not.toBe(bad);
      expect(id).toMatch(/^[0-9a-f-]{36}$/);
    }
  });

  it("gives each request a distinct id", async () => {
    const [a, b] = await Promise.all([request(app).get("/health"), request(app).get("/health")]);
    expect(a.headers["x-request-id"]).not.toBe(b.headers["x-request-id"]);
  });

  it("puts the same id in the header and in the error envelope", async () => {
    // requireAuth rejects before any database access, so this stays a unit test.
    const res = await request(app).get("/api/v1/bookings").set("x-request-id", "corr-0001-abc");
    expect(res.status).toBe(401);
    expect(res.headers["x-request-id"]).toBe("corr-0001-abc");
    expect(res.body.error.requestId).toBe("corr-0001-abc");
  });
});
