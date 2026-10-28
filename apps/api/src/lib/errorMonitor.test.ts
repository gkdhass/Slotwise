import { afterEach, describe, expect, it } from "vitest";
import http from "node:http";
import type { AddressInfo } from "node:net";
import { buildReport, captureError, redactPath } from "./errorMonitor.js";

const servers: http.Server[] = [];

afterEach(async () => {
  await Promise.all(
    servers.splice(0).map((s) => new Promise<void>((resolve) => s.close(() => resolve()))),
  );
});

function listen(handler: http.RequestListener): Promise<string> {
  const server = http.createServer(handler);
  servers.push(server);
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      resolve(`http://127.0.0.1:${(server.address() as AddressInfo).port}`);
    });
  });
}

describe("error monitor", () => {
  it("masks management tokens in the path but keeps normal slugs", () => {
    expect(redactPath("/api/v1/manage/8f14e45fceea167a5a36dedd4bea2543aabbccdd00112233445566778899aabb/cancel")).toBe(
      "/api/v1/manage/[redacted]/cancel",
    );
    expect(redactPath("/manage/8f14e45fceea167a5a36dedd4bea2543aabbccdd00112233445566778899aabb")).toBe(
      "/manage/[redacted]",
    );
    expect(redactPath("/api/v1/public/intro-tutoring/slots")).toBe("/api/v1/public/intro-tutoring/slots");
  });

  it("drops the query string, which can carry tokens", () => {
    expect(redactPath("/api/v1/public/x/slots?token=secret&from=2027-01-01")).toBe("/api/v1/public/x/slots");
  });

  it("builds a report with name, message, stack and the request id", () => {
    const err = new Error("database exploded");
    const report = buildReport(err, { requestId: "req-42", method: "POST", path: "/api/v1/bookings" });
    expect(report).toMatchObject({
      requestId: "req-42",
      method: "POST",
      path: "/api/v1/bookings",
      status: 500,
      name: "Error",
      message: "database exploded",
    });
    expect(report.stack).toContain("Error: database exploded");
  });

  it("handles a thrown non-Error without crashing", () => {
    const report = buildReport("plain string", { requestId: "r", method: "GET", path: "/x" });
    expect(report.message).toBe("plain string");
  });

  it("does nothing beyond logging when no webhook is configured", () => {
    expect(() => captureError(new Error("boom"), { requestId: "r1", method: "GET", path: "/x" }, {})).not.toThrow();
  });

  it("posts a redacted report to the configured webhook", async () => {
    const received: Array<Record<string, unknown>> = [];
    const url = await listen((req, res) => {
      let body = "";
      req.on("data", (c) => (body += c));
      req.on("end", () => {
        received.push(JSON.parse(body));
        res.writeHead(204).end();
      });
    });

    captureError(
      new Error("kaboom"),
      {
        requestId: "req-77",
        method: "GET",
        path: "/api/v1/manage/8f14e45fceea167a5a36dedd4bea2543aabbccdd00112233445566778899aabb",
      },
      { ERROR_MONITOR_WEBHOOK_URL: url },
    );

    // The POST is fire-and-forget; give it a moment.
    for (let i = 0; i < 50 && received.length === 0; i += 1) {
      await new Promise((r) => setTimeout(r, 20));
    }

    expect(received).toHaveLength(1);
    expect(received[0]).toMatchObject({
      service: "slotwise-api",
      requestId: "req-77",
      path: "/api/v1/manage/[redacted]",
      message: "kaboom",
      status: 500,
    });
    expect(JSON.stringify(received[0])).not.toContain("8f14e45f");
  });

  it("swallows an unreachable webhook instead of failing the request", async () => {
    // Port 1 is not listening: the fetch rejects, and that must not escape.
    expect(() =>
      captureError(new Error("boom"), { requestId: "r2", method: "GET", path: "/x" }, {
        ERROR_MONITOR_WEBHOOK_URL: "http://127.0.0.1:1/nothing",
      }),
    ).not.toThrow();
  });
});
