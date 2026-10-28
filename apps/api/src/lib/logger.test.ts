import { describe, expect, it } from "vitest";
import { CENSOR, createLogger, REDACT_PATHS } from "./logger.js";

/** Collects log lines instead of writing them to stdout. */
function capture() {
  const lines: string[] = [];
  const stream = {
    write(chunk: string) {
      lines.push(chunk);
      return true;
    },
  } as unknown as NodeJS.WritableStream;
  return { log: createLogger(stream, "debug"), lines };
}

describe("structured logger", () => {
  it("writes one JSON object per line with level, time, service and message", () => {
    const { log, lines } = capture();
    log.info({ requestId: "req-1234-abcd" }, "hello");
    const entry = JSON.parse(lines[0]);
    expect(entry.msg).toBe("hello");
    expect(entry.level).toBe(30);
    expect(entry.service).toBe("slotwise-api");
    expect(entry.requestId).toBe("req-1234-abcd");
    expect(typeof entry.time).toBe("string");
  });

  it("redacts session cookies, CSRF tokens and worker secrets", () => {
    const { log, lines } = capture();
    log.info(
      {
        req: {
          headers: {
            cookie: "session=super-secret-session",
            authorization: "Bearer super-secret-bearer",
            "x-csrf-token": "super-secret-csrf",
            "x-worker-secret": "super-secret-worker",
          },
        },
      },
      "request",
    );
    const line = lines[0];
    expect(line).not.toContain("super-secret");
    expect(line).toContain(CENSOR);
    expect(JSON.parse(line).req.headers.cookie).toBe(CENSOR);
  });

  it("redacts passwords and tokens in logged payloads", () => {
    const { log, lines } = capture();
    log.debug(
      { password: "hunter2", newPassword: "hunter3", token: "tok_live_123", req: { body: { password: "hunter4" } } },
      "payload",
    );
    const line = lines[0];
    expect(line).not.toContain("hunter");
    expect(line).not.toContain("tok_live_123");
    const entry = JSON.parse(line);
    expect(entry.password).toBe(CENSOR);
    expect(entry.token).toBe(CENSOR);
    expect(entry.req.body.password).toBe(CENSOR);
  });

  it("keeps non-secret fields intact so logs stay useful", () => {
    const { log, lines } = capture();
    log.info({ requestId: "abc", req: { method: "POST", url: "/api/v1/public/intro-tutoring/bookings" } }, "handled");
    const entry = JSON.parse(lines[0]);
    expect(entry.req.method).toBe("POST");
    expect(entry.req.url).toBe("/api/v1/public/intro-tutoring/bookings");
  });

  it("declares a redaction path for every credential header", () => {
    for (const header of ["authorization", "cookie", "x-csrf-token", "x-worker-secret"]) {
      expect(REDACT_PATHS.some((p) => p.includes(header))).toBe(true);
    }
  });
});
