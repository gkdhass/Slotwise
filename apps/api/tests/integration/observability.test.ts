import { describe, it, expect, afterAll } from "vitest";
import { app, prisma, request } from "./helpers.js";

/**
 * NFR-05 operational surface: the two health probes and request correlation.
 * These need a real database, so they live in the integration suite.
 */
describe("health and observability", () => {
  afterAll(async () => {
    await prisma.$disconnect();
  });

  it("GET /health is liveness only and does not require the database", async () => {
    const res = await request(app).get("/health");
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ status: "ok", service: "slotwise-api" });
    expect(res.headers["x-request-id"]).toBeTruthy();
  });

  it("GET /health/ready confirms the database answers", async () => {
    const res = await request(app).get("/health/ready");
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ status: "ok", database: "ok" });
  });

  it("correlates the response header with the error envelope", async () => {
    const res = await request(app).get("/api/v1/public/does-not-exist/slots").set("x-request-id", "corr-health-0001");
    expect(res.status).toBe(404);
    expect(res.headers["x-request-id"]).toBe("corr-health-0001");
    expect(res.body.error.requestId).toBe("corr-health-0001");
  });

  it("keeps request ids unique per request", async () => {
    const [a, b] = await Promise.all([request(app).get("/health"), request(app).get("/health")]);
    expect(a.headers["x-request-id"]).not.toBe(b.headers["x-request-id"]);
  });
});
