import { describe, it, expect, afterAll, beforeEach } from "vitest";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  assertProductionSafety,
  trustProxyHops,
  trustProxySetting,
} from "../../src/lib/config.js";
import { resetRateLimits } from "../../src/middleware/rateLimit.js";
import { app, csrfReadyAgent, prisma, uniqueEmail } from "../integration/helpers.js";

/**
 * X-Forwarded-For / trust-proxy hardening (Task A).
 *
 * Two things are proven here:
 *   1. `TRUST_PROXY` is parsed and gated correctly, and production cannot boot
 *      with a setting that lets a client choose its own `req.ip`.
 *   2. The property that actually matters: rotating the spoofable part of
 *      `X-Forwarded-For` cannot reset a per-IP rate-limit bucket.
 *
 * Express semantics confirmed empirically against express 4.21.2:
 *   trust proxy = false : `req.ip` is the socket address, XFF ignored entirely.
 *   trust proxy = 1     : `req.ip` is the RIGHTMOST XFF entry, i.e. the address
 *                         appended by the single proxy in front of us. Anything
 *                         a client prepends is ignored.
 */

const ORIGINAL_TRUST_PROXY = app.get("trust proxy");
const ORIGINAL_LOGIN_MAX = process.env.RATE_LIMIT_LOGIN_MAX;

beforeEach(() => {
  resetRateLimits();
});

afterAll(async () => {
  app.set("trust proxy", ORIGINAL_TRUST_PROXY);
  if (ORIGINAL_LOGIN_MAX === undefined) delete process.env.RATE_LIMIT_LOGIN_MAX;
  else process.env.RATE_LIMIT_LOGIN_MAX = ORIGINAL_LOGIN_MAX;
  await prisma.$disconnect();
});

function setRateLimitEnv() {
  process.env.RATE_LIMIT_LOGIN_MAX = "3";
}

async function loginAttempt(email: string, xff?: string) {
  const agent = await csrfReadyAgent();
  let req = agent.post("/api/v1/auth/login").send({ email, password: "wrong-password" });
  if (xff !== undefined) req = req.set("X-Forwarded-For", xff);
  return req;
}

describe("trustProxySetting() parsing", () => {
  it("defaults to false when TRUST_PROXY is unset or explicitly off", () => {
    expect(trustProxySetting({})).toBe(false);
    expect(trustProxySetting({ TRUST_PROXY: "" })).toBe(false);
    expect(trustProxySetting({ TRUST_PROXY: "  " })).toBe(false);
    expect(trustProxySetting({ TRUST_PROXY: "false" })).toBe(false);
    expect(trustProxySetting({ TRUST_PROXY: "0" })).toBe(false);
  });

  it("parses an exact hop count as a number", () => {
    expect(trustProxySetting({ TRUST_PROXY: "1" })).toBe(1);
    expect(trustProxySetting({ TRUST_PROXY: "2" })).toBe(2);
    expect(trustProxySetting({ TRUST_PROXY: " 1 " })).toBe(1);
    expect(trustProxySetting({ TRUST_PROXY: "12" })).toBe(12);
  });

  it("leaves non-integer Express forms for Express to interpret (non-production convenience)", () => {
    expect(trustProxySetting({ TRUST_PROXY: "loopback" })).toBe("loopback");
    expect(trustProxySetting({ TRUST_PROXY: "true" })).toBe("true");
    expect(trustProxySetting({ TRUST_PROXY: "10.0.0.0/8" })).toBe("10.0.0.0/8");
  });

  it("trustProxyHops() only accepts an exact positive integer", () => {
    expect(trustProxyHops({ TRUST_PROXY: "1" })).toBe(1);
    expect(trustProxyHops({ TRUST_PROXY: "3" })).toBe(3);
    for (const raw of ["", "0", "false", "true", "loopback", "1.5", "-1", "0x2", "1e3", "abc"]) {
      expect(trustProxyHops({ TRUST_PROXY: raw }), `TRUST_PROXY=${raw}`).toBeNull();
    }
  });
});

describe("production startup guard requires an exact hop count", () => {
  const safe = {
    NODE_ENV: "production",
    CSRF_DISABLED: "false",
    SESSION_SECRET: "a-production-session-secret",
    DATABASE_URL: "postgresql://u:p@db.example/app",
  } as NodeJS.ProcessEnv;

  it("accepts an exact positive integer", () => {
    expect(() => assertProductionSafety({ ...safe, TRUST_PROXY: "1" })).not.toThrow();
    expect(() => assertProductionSafety({ ...safe, TRUST_PROXY: "2" })).not.toThrow();
  });

  it("refuses unset, zero, boolean and pattern values", () => {
    for (const trustProxy of [undefined, "", "0", "false", "true", "loopback", "1.5"]) {
      expect(
        () => assertProductionSafety({ ...safe, TRUST_PROXY: trustProxy } as NodeJS.ProcessEnv),
        `TRUST_PROXY=${String(trustProxy)}`,
      ).toThrow(/TRUST_PROXY/);
    }
  });

  it("does not apply the requirement outside production", () => {
    expect(() =>
      assertProductionSafety({ NODE_ENV: "test", TRUST_PROXY: undefined } as unknown as NodeJS.ProcessEnv),
    ).not.toThrow();
  });

  it("the real entry point refuses to boot in production with TRUST_PROXY unset", async () => {
    const here = path.dirname(fileURLToPath(import.meta.url));
    const apiRoot = path.resolve(here, "../..");

    const childEnv: NodeJS.ProcessEnv = {
      ...process.env,
      NODE_ENV: "production",
      CSRF_DISABLED: "false",
      SESSION_SECRET: "a-production-session-secret",
      PORT: "0",
      DATABASE_URL: process.env.DATABASE_URL ?? "postgresql://u:p@127.0.0.1:1/none",
    };
    delete childEnv.TRUST_PROXY;

    const result = await new Promise<{ code: number | null; stderr: string; stdout: string }>((resolve) => {
      const child = spawn(process.execPath, ["--import", "tsx", "src/index.ts"], {
        cwd: apiRoot,
        env: childEnv,
      });
      let stderr = "";
      let stdout = "";
      child.stderr.on("data", (d) => (stderr += String(d)));
      child.stdout.on("data", (d) => (stdout += String(d)));
      const timer = setTimeout(() => {
        child.kill();
        resolve({ code: -1, stderr: `${stderr}\nTIMEOUT`, stdout });
      }, 60_000);
      child.on("exit", (code) => {
        clearTimeout(timer);
        resolve({ code, stderr, stdout });
      });
    });

    expect(result.code).not.toBe(0);
    expect(result.code).not.toBe(-1); // must exit on its own, not be killed
    expect(`${result.stderr}${result.stdout}`).toMatch(/TRUST_PROXY/);
    expect(`${result.stderr}${result.stdout}`).not.toMatch(/listening on/);
  }, 90_000);
});

describe("rate-limit keys cannot be rotated through X-Forwarded-For", () => {
  it("with trust proxy off, a rotating header does not reset the bucket", async () => {
    app.set("trust proxy", false);
    setRateLimitEnv();
    const email = uniqueEmail("xff-off");

    // Same email (so the email half of the key is constant) and a fresh
    // attacker-chosen IP on every request. If XFF were believed, every request
    // would land in a new bucket and none of them would be limited.
    for (let i = 0; i < 3; i += 1) {
      const res = await loginAttempt(email, `203.0.113.${10 + i}`);
      expect(res.status, `request ${i + 1} should be allowed`).toBe(401);
    }
    const limited = await loginAttempt(email, "203.0.113.250");
    expect(limited.status).toBe(429);
    expect(limited.body.error.code).toBe("RATE_LIMITED");
  });

  it("with trust proxy = 1, rotating the client-supplied leftmost entry does not reset the bucket", async () => {
    app.set("trust proxy", 1);
    setRateLimitEnv();
    const email = uniqueEmail("xff-on");

    // The proxy appends the real peer (198.51.100.7) to whatever the client
    // sent. Only that appended address is trusted, so rotating the prefix must
    // not open a new bucket.
    for (let i = 0; i < 3; i += 1) {
      const res = await loginAttempt(email, `203.0.113.${10 + i}, 198.51.100.7`);
      expect(res.status, `request ${i + 1} should be allowed`).toBe(401);
    }
    const limited = await loginAttempt(email, "192.0.2.77, 198.51.100.7");
    expect(limited.status).toBe(429);
    expect(limited.body.error.code).toBe("RATE_LIMITED");
  });

  it("with trust proxy = 1, the rightmost (proxy-appended) address is the key", async () => {
    app.set("trust proxy", 1);
    setRateLimitEnv();
    const email = uniqueEmail("xff-rightmost");

    for (let i = 0; i < 3; i += 1) {
      expect((await loginAttempt(email, "203.0.113.10, 198.51.100.7")).status).toBe(401);
    }
    expect((await loginAttempt(email, "203.0.113.10, 198.51.100.7")).status).toBe(429);

    // A genuinely different peer behind the same proxy gets its own bucket.
    const other = await loginAttempt(email, "203.0.113.10, 198.51.100.8");
    expect(other.status).toBe(401);
  });

  it("with trust proxy off, two different header values are the same bucket", async () => {
    app.set("trust proxy", false);
    setRateLimitEnv();
    const email = uniqueEmail("xff-ignore");

    expect((await loginAttempt(email, "198.51.100.7")).status).toBe(401);
    expect((await loginAttempt(email, "198.51.100.8")).status).toBe(401);
    expect((await loginAttempt(email, "198.51.100.9")).status).toBe(401);
    // All three above are the same socket peer, so this fourth one is over the
    // limit regardless of which header value it carries.
    expect((await loginAttempt(email, "198.51.100.10")).status).toBe(429);
  });
});
