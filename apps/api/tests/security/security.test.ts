import { describe, it, expect, afterAll, beforeEach } from "vitest";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { assertProductionSafety, corsAllowList, csrfBypassActive } from "../../src/lib/config.js";
import { resetRateLimits } from "../../src/middleware/rateLimit.js";
import {
  app,
  createEvent,
  createOwner,
  csrfReadyAgent,
  prisma,
  purgeUsers,
  request,
  uniqueEmail,
} from "../integration/helpers.js";

const createdUserIds: string[] = [];
const track = (id: string) => {
  createdUserIds.push(id);
  return id;
};

const ORIGINAL_ENV = { ...process.env };

beforeEach(() => {
  resetRateLimits();
});

afterAll(async () => {
  await purgeUsers(createdUserIds);
  // Restore anything a test changed.
  for (const key of Object.keys(process.env)) {
    if (!(key in ORIGINAL_ENV)) delete process.env[key];
  }
  Object.assign(process.env, ORIGINAL_ENV);
  await prisma.$disconnect();
});

/** A supertest agent that has already picked up a CSRF cookie and echoes it. */
async function csrfAgent() {
  const agent = await csrfReadyAgent();
  const token = (agent as unknown as { csrfToken: string }).csrfToken;
  expect(token).toBeTruthy();
  return { agent, token };
}

// ---------------------------------------------------------------------------
// CSRF — enforced in this suite (vitest.security.config.ts sets CSRF_DISABLED=false)
// ---------------------------------------------------------------------------

describe("CSRF protection with CSRF enforcement enabled", () => {
  it("the bypass is genuinely off in this suite", () => {
    expect(process.env.CSRF_DISABLED).toBe("false");
    expect(csrfBypassActive()).toBe(false);
  });

  it("a mutation without the double-submit header is rejected with 403", async () => {
    const agent = request.agent(app);
    const email = uniqueEmail("csrf-none");
    // Obtain the cookie but deliberately do not echo it back.
    await agent.get("/api/v1/auth/csrf");

    const res = await agent.post("/api/v1/auth/register").send({ email, password: "password-123" });
    expect(res.status).toBe(403);
    expect(res.body.error.code).toBe("FORBIDDEN");
    expect(res.body.error.message).toMatch(/CSRF/i);

    // Nothing was created.
    expect(await prisma.user.count({ where: { email } })).toBe(0);
  });

  it("a mismatched cookie/header pair is rejected", async () => {
    const { agent } = await csrfAgent();
    const res = await agent
      .post("/api/v1/auth/login")
      .set("x-csrf-token", "0".repeat(48))
      .send({ email: uniqueEmail("csrf-mismatch"), password: "password-123" });
    expect(res.status).toBe(403);
    expect(res.body.error.code).toBe("FORBIDDEN");
  });

  it("a header with no cookie is rejected", async () => {
    const res = await request(app)
      .post("/api/v1/auth/login")
      .set("x-csrf-token", "a".repeat(48))
      .send({ email: uniqueEmail("csrf-nocookie"), password: "password-123" });
    expect(res.status).toBe(403);
  });

  it("register, login and logout succeed end-to-end once the token is echoed", async () => {
    const { agent } = await csrfAgent();
    const email = uniqueEmail("csrf-ok");

    const reg = await agent.post("/api/v1/auth/register").send({ email, password: "password-123" });
    expect(reg.status).toBe(201);
    track(reg.body.id);

    const login = await agent.post("/api/v1/auth/login").send({ email, password: "password-123" });
    expect(login.status).toBe(200);

    const me = await agent.get("/api/v1/auth/me");
    expect(me.status).toBe(200);
    expect(me.body.email).toBe(email);

    const logout = await agent.post("/api/v1/auth/logout");
    expect(logout.status).toBe(204);

    const afterLogout = await agent.get("/api/v1/auth/me");
    expect(afterLogout.status).toBe(401);
  });

  it("authenticated owner mutations are CSRF-protected too", async () => {
    const { agent } = await csrfAgent();
    const email = uniqueEmail("csrf-owner");
    await agent.post("/api/v1/auth/register").send({ email, password: "password-123" });
    const user = await prisma.user.findUniqueOrThrow({ where: { email } });
    track(user.id);
    await prisma.user.update({ where: { id: user.id }, data: { emailVerifiedAt: new Date() } });
    const login = await agent.post("/api/v1/auth/login").send({ email, password: "password-123" });
    expect(login.status).toBe(200);

    // Without the header: forbidden, and no event type is created.
    const blocked = await agent.post("/api/v1/event-types").set("x-csrf-token", "").send({
      title: "CSRF blocked",
      durationMinutes: 30,
      timezone: "UTC",
    });
    expect(blocked.status).toBe(403);
    expect(await prisma.eventType.count({ where: { userId: user.id } })).toBe(0);

    // With the header: allowed.
    const allowed = await agent.post("/api/v1/event-types").send({
      title: "CSRF allowed",
      durationMinutes: 30,
      timezone: "UTC",
    });
    expect(allowed.status).toBe(201);
  });

  it("safe methods are exempt from the token check", async () => {
    const res = await request(app).get("/api/v1/auth/me");
    // 401 (no session) but never 403 (CSRF).
    expect(res.status).toBe(401);
  });
});

// ---------------------------------------------------------------------------
// Rate limiting
// ---------------------------------------------------------------------------

describe("rate limiting returns 429 with Retry-After", () => {
  it("login is limited per IP + email", async () => {
    process.env.RATE_LIMIT_LOGIN_MAX = "3";
    const email = uniqueEmail("rl-login");
    const agent = await csrfReadyAgent();

    for (let i = 0; i < 3; i += 1) {
      const res = await agent.post("/api/v1/auth/login").send({ email, password: "wrong-password" });
      expect(res.status).toBe(401);
    }

    const limited = await agent.post("/api/v1/auth/login").send({ email, password: "wrong-password" });
    expect(limited.status).toBe(429);
    expect(limited.body.error.code).toBe("RATE_LIMITED");
    expect(Number(limited.headers["retry-after"])).toBeGreaterThan(0);
    expect(limited.headers["x-ratelimit-limit"]).toBe("3");

    // A different email still has its own bucket.
    const other = await agent.post("/api/v1/auth/login").send({ email: uniqueEmail("rl-other"), password: "x" });
    expect(other.status).toBe(401);
  });

  it("the slots endpoint is rate limited", async () => {
    process.env.RATE_LIMIT_SLOTS_MAX = "2";
    const { agent, userId } = await createOwner({ prefix: "rl-slots" });
    track(userId);
    const ev = await createEvent(agent, { title: "Rate limited slots" });
    const q = { from: "2027-06-07T00:00:00.000Z", to: "2027-06-08T00:00:00.000Z", tz: "UTC" };

    expect((await request(app).get(`/api/v1/public/${ev.slug}/slots`).query(q)).status).toBe(200);
    expect((await request(app).get(`/api/v1/public/${ev.slug}/slots`).query(q)).status).toBe(200);
    const limited = await request(app).get(`/api/v1/public/${ev.slug}/slots`).query(q);
    expect(limited.status).toBe(429);
    expect(limited.body.error.code).toBe("RATE_LIMITED");
  });

  it("the booking endpoint is rate limited", async () => {
    process.env.RATE_LIMIT_BOOKING_MAX = "2";
    const { agent, userId } = await createOwner({ prefix: "rl-book" });
    track(userId);
    const ev = await createEvent(agent, { title: "Rate limited booking" });

    for (let i = 0; i < 2; i += 1) {
      const res = await request(app).post(`/api/v1/public/${ev.slug}/bookings`).send({});
      expect(res.status).toBe(400); // reached the handler, failed validation
    }
    const limited = await request(app).post(`/api/v1/public/${ev.slug}/bookings`).send({});
    expect(limited.status).toBe(429);
    expect(limited.body.error.code).toBe("RATE_LIMITED");
    expect(Number(limited.headers["retry-after"])).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// Transport / header hygiene
// ---------------------------------------------------------------------------

describe("security headers and CORS", () => {
  it("helmet sets the baseline security headers and a no-referrer policy", async () => {
    const res = await request(app).get("/health");
    expect(res.status).toBe(200);
    expect(res.headers["x-content-type-options"]).toBe("nosniff");
    expect(res.headers["x-frame-options"]).toBe("SAMEORIGIN");
    expect(res.headers["referrer-policy"]).toBe("no-referrer");
    expect(res.headers["content-security-policy"]).toBeTruthy();
    expect(res.headers["cross-origin-opener-policy"]).toBe("same-origin");
    expect(res.headers["strict-transport-security"]).toBeTruthy();
    expect(res.headers["x-powered-by"]).toBeUndefined();
  });

  it("CORS echoes only allow-listed origins and never uses a wildcard", async () => {
    const allowList = corsAllowList();
    expect(allowList.length).toBeGreaterThan(0);
    const allowedOrigin = allowList[0];

    const allowed = await request(app)
      .options("/api/v1/auth/login")
      .set("Origin", allowedOrigin)
      .set("Access-Control-Request-Method", "POST");
    expect(allowed.headers["access-control-allow-origin"]).toBe(allowedOrigin);
    expect(allowed.headers["access-control-allow-credentials"]).toBe("true");
    expect(allowed.headers["access-control-allow-origin"]).not.toBe("*");

    const blocked = await request(app)
      .options("/api/v1/auth/login")
      .set("Origin", "https://attacker.example")
      .set("Access-Control-Request-Method", "POST");
    expect(blocked.headers["access-control-allow-origin"]).toBeUndefined();
  });

  it("the manage route forbids referrer leakage and caching", async () => {
    const res = await request(app).get(`/api/v1/manage/${"c".repeat(64)}`);
    expect(res.headers["referrer-policy"]).toBe("no-referrer");
    expect(res.headers["cache-control"]).toBe("no-store");
    // And the denial is generic.
    expect(res.status).toBe(404);
    expect(JSON.stringify(res.body)).not.toContain("invitee");
  });
});

// ---------------------------------------------------------------------------
// The test-only CSRF bypass must be impossible in production
// ---------------------------------------------------------------------------

describe("production startup guard", () => {
  it("csrfBypassActive() is false whenever NODE_ENV is production", () => {
    expect(csrfBypassActive({ NODE_ENV: "production", CSRF_DISABLED: "true" })).toBe(false);
    expect(csrfBypassActive({ NODE_ENV: "production", CSRF_DISABLED: "false" })).toBe(false);
    expect(csrfBypassActive({ NODE_ENV: "test", CSRF_DISABLED: "true" })).toBe(true);
    expect(csrfBypassActive({ NODE_ENV: "test", CSRF_DISABLED: "false" })).toBe(false);
    expect(csrfBypassActive({ NODE_ENV: "development", CSRF_DISABLED: "true" })).toBe(false);
  });

  it("assertProductionSafety throws for CSRF_DISABLED=true, and accepts a safe production env", () => {
    const safe = {
      NODE_ENV: "production",
      CSRF_DISABLED: "false",
      SESSION_SECRET: "a-production-session-secret",
      DATABASE_URL: "postgresql://u:p@db.example/app",
    };
    expect(() => assertProductionSafety(safe as NodeJS.ProcessEnv)).not.toThrow();

    expect(() =>
      assertProductionSafety({ ...safe, CSRF_DISABLED: "true" } as NodeJS.ProcessEnv),
    ).toThrow(/CSRF_DISABLED/);

    expect(() =>
      assertProductionSafety({ ...safe, SESSION_SECRET: undefined } as unknown as NodeJS.ProcessEnv),
    ).toThrow(/SESSION_SECRET/);

    expect(() =>
      assertProductionSafety({ ...safe, DATABASE_URL: undefined } as unknown as NodeJS.ProcessEnv),
    ).toThrow(/DATABASE_URL/);

    // In test/development the guard is inert.
    expect(() =>
      assertProductionSafety({ NODE_ENV: "test", CSRF_DISABLED: "true" } as NodeJS.ProcessEnv),
    ).not.toThrow();
  });

  it("the real entry point refuses to boot in production with the CSRF bypass flag set", async () => {
    const here = path.dirname(fileURLToPath(import.meta.url));
    const apiRoot = path.resolve(here, "../..");

    const result = await new Promise<{ code: number | null; stderr: string; stdout: string }>((resolve) => {
      const child = spawn(process.execPath, ["--import", "tsx", "src/index.ts"], {
        cwd: apiRoot,
        env: {
          ...process.env,
          NODE_ENV: "production",
          CSRF_DISABLED: "true",
          PORT: "0",
          // Keep the child from touching the real database before it throws.
          DATABASE_URL: process.env.DATABASE_URL ?? "postgresql://u:p@127.0.0.1:1/none",
        },
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
    expect(`${result.stderr}${result.stdout}`).toMatch(/CSRF_DISABLED/);
    expect(`${result.stderr}${result.stdout}`).not.toMatch(/listening on/);
  }, 90_000);
});
