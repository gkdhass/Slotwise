import request from "supertest";
import app from "../../src/index.js";
import { prisma } from "../../src/lib/prisma.js";

export type Agent = ReturnType<typeof request.agent>;

export const PASSWORD = "password-123";

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

/** Reads the double-submit CSRF cookie out of a response's Set-Cookie header. */
export function csrfCookieFrom(res: { headers: Record<string, unknown> }): string | null {
  const raw = res.headers["set-cookie"];
  const list = Array.isArray(raw) ? raw : typeof raw === "string" ? [raw] : [];
  for (const cookie of list) {
    const m = String(cookie).match(/^csrf_token=([^;]+)/);
    if (m) return m[1];
  }
  return null;
}

/**
 * Performs the CSRF handshake and then makes the agent echo the token on every
 * mutating request. Harmless when the suite runs with the bypass enabled, and
 * required by the security suite where CSRF is enforced.
 */
export async function csrfReadyAgent(): Promise<Agent> {
  const agent = request.agent(app);
  const boot = await agent.get("/api/v1/auth/csrf");
  const token = csrfCookieFrom(boot as unknown as { headers: Record<string, unknown> });
  if (!token) throw new Error("no csrf cookie issued");
  const patchable = agent as unknown as Record<string, (url: string) => any>;
  for (const method of ["post", "put", "patch", "delete"] as const) {
    const original = patchable[method].bind(agent);
    patchable[method] = (url: string) => original(url).set("x-csrf-token", token);
  }
  (agent as unknown as { csrfToken?: string }).csrfToken = token;
  return agent;
}

/** Registers an owner through the API and optionally marks the email verified. */
export async function createOwner(opts: { prefix?: string; verified?: boolean } = {}) {
  const email = uniqueEmail(opts.prefix ?? "owner");
  const agent = await csrfReadyAgent();
  const reg = await agent.post("/api/v1/auth/register").send({ email, password: PASSWORD });
  if (reg.status !== 201) throw new Error(`register failed: ${reg.status} ${JSON.stringify(reg.body)}`);
  const user = await prisma.user.findUniqueOrThrow({ where: { email } });
  if (opts.verified !== false) {
    await prisma.user.update({ where: { id: user.id }, data: { emailVerifiedAt: new Date() } });
  }
  const login = await agent.post("/api/v1/auth/login").send({ email, password: PASSWORD });
  if (login.status !== 200) throw new Error(`login failed: ${login.status} ${JSON.stringify(login.body)}`);
  return { email, userId: user.id, agent, password: PASSWORD };
}

export type CreatedEvent = {
  id: string;
  slug: string;
  durationMinutes: number;
  timezone: string;
};

/** Creates an event type plus availability through the API. */
export async function createEvent(
  agent: Agent,
  opts: {
    title?: string;
    durationMinutes?: number;
    timezone?: string;
    locationType?: "online" | "phone" | "custom";
    rules?: Array<{ weekday: number; startLocal: string; endLocal: string }>;
    publish?: boolean;
  } = {},
): Promise<CreatedEvent> {
  const title = opts.title ?? `Session ${Math.random().toString(36).slice(2, 7)}`;
  const durationMinutes = opts.durationMinutes ?? 30;
  const timezone = opts.timezone ?? "UTC";
  const created = await agent.post("/api/v1/event-types").send({
    title,
    durationMinutes,
    timezone,
    locationType: opts.locationType ?? "online",
    locationDetails: "Video link",
    description: "Test session",
  });
  if (created.status !== 201) throw new Error(`create event failed: ${created.status} ${JSON.stringify(created.body)}`);
  const rules =
    opts.rules ?? [0, 1, 2, 3, 4, 5, 6].map((weekday) => ({ weekday, startLocal: "00:00", endLocal: "23:59" }));
  const saved = await agent.put(`/api/v1/event-types/${created.body.id}/availability`).send(
    rules.map((r) => ({ ...r, timezone })),
  );
  if (saved.status !== 200) throw new Error(`availability failed: ${saved.status} ${JSON.stringify(saved.body)}`);
  if (opts.publish !== false) {
    const pub = await agent.patch(`/api/v1/event-types/${created.body.id}`).send({ isPublished: true });
    if (pub.status !== 200) throw new Error(`publish failed: ${pub.status} ${JSON.stringify(pub.body)}`);
  }
  return { id: created.body.id, slug: created.body.slug, durationMinutes, timezone };
}

export type Slot = { startAt: string; endAt: string; label: string };

/** Asks the public slots endpoint for the first N slots in a window. */
export async function listSlots(
  slug: string,
  opts: { tz?: string; startOffsetDays?: number; spanDays?: number } = {},
): Promise<Slot[]> {
  const tz = opts.tz ?? "UTC";
  const from = new Date(Date.now() + (opts.startOffsetDays ?? 1) * 86_400_000);
  const to = new Date(from.getTime() + (opts.spanDays ?? 21) * 86_400_000);
  const res = await request(app)
    .get(`/api/v1/public/${slug}/slots`)
    .query({ from: from.toISOString(), to: to.toISOString(), tz });
  if (res.status !== 200) throw new Error(`slots failed: ${res.status} ${JSON.stringify(res.body)}`);
  return res.body as Slot[];
}

export async function firstSlot(slug: string, opts: { tz?: string } = {}): Promise<Slot> {
  const slots = await listSlots(slug, { tz: opts.tz ?? "UTC" });
  if (slots.length === 0) throw new Error(`no slots for ${slug}`);
  return slots[0];
}

export async function book(
  slug: string,
  slot: Slot,
  opts: { name?: string; email?: string; tz?: string; idempotencyKey?: string; note?: string } = {},
) {
  return request(app)
    .post(`/api/v1/public/${slug}/bookings`)
    .send({
      startAt: slot.startAt,
      timezone: opts.tz ?? "UTC",
      invitee: {
        name: opts.name ?? "Test Invitee",
        email: opts.email ?? uniqueEmail("invitee"),
        note: opts.note,
      },
      idempotencyKey: opts.idempotencyKey ?? `idem-${Math.random().toString(36).slice(2)}`,
    });
}

/** Deletes every row owned by the given users (bookings first, FKs are RESTRICT). */
export async function purgeUsers(userIds: string[]): Promise<void> {
  if (userIds.length === 0) return;
  const bookings = await prisma.booking.findMany({ where: { userId: { in: userIds } }, select: { id: true } });
  const bookingIds = bookings.map((b) => b.id);
  await prisma.outboxJob.deleteMany({ where: { bookingId: { in: bookingIds } } });
  await prisma.booking.deleteMany({ where: { id: { in: bookingIds } } });
  await prisma.eventType.deleteMany({ where: { userId: { in: userIds } } });
  await prisma.session.deleteMany({ where: { userId: { in: userIds } } });
  await prisma.user.deleteMany({ where: { id: { in: userIds } } });
}

export { app, prisma, request };
