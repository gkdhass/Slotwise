import type {
  EventType,
  AvailabilityRule,
  Slot,
  Booking,
  CreateBookingInput,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:4000";

export type ApiErrorCode =
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "SLOT_UNAVAILABLE"
  | "BOOKING_NOT_ACTIVE"
  | "CONFLICT"
  | "VALIDATION_ERROR"
  | "UNPROCESSABLE"
  | "RATE_LIMITED"
  | "NETWORK"
  | "INTERNAL"
  | string;

/**
 * Every failed call surfaces as an ApiError so screens can react to the HTTP
 * status (`status`) and show a single, human message (`userMessage`).
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode;
  readonly fieldErrors: Record<string, string>;
  readonly requestId?: string;

  constructor(status: number, code: ApiErrorCode, message: string, fieldErrors: Record<string, string> = {}, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
    this.requestId = requestId;
  }

  get userMessage(): string {
    if (this.code === "SLOT_UNAVAILABLE" || this.status === 409) {
      return this.message || "That time is no longer available. Choose another slot.";
    }
    return this.message;
  }
}

export function messageForStatus(status: number, code?: string, serverMessage?: string): string {
  if (code === "SLOT_UNAVAILABLE" || status === 409) {
    return serverMessage || "That time was just taken. Pick another slot.";
  }
  if (code === "BOOKING_NOT_ACTIVE") {
    return "This booking can no longer be changed.";
  }
  switch (status) {
    case 400:
      return "Check the highlighted fields and try again.";
    case 401:
      return "Your session has expired. Sign in again to continue.";
    case 403:
      return "You do not have permission to do that.";
    case 404:
      return "We could not find that page.";
    case 422:
      return serverMessage || "That request is not valid. Check the details and try again.";
    case 429:
      return "Too many attempts. Wait a minute and try again.";
    case 500:
    case 502:
    case 503:
      return "Something went wrong on our side. Try again.";
    default:
      return serverMessage || "Something went wrong. Try again.";
  }
}

function csrfToken(): string | null {
  const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

/**
 * The API hands out its double-submit CSRF cookie from any GET. Fetch it once
 * before the first mutation so a fresh visitor can sign in.
 */
let csrfBootstrap: Promise<void> | null = null;

async function ensureCsrf(): Promise<void> {
  if (csrfToken()) return;
  if (!csrfBootstrap) {
    csrfBootstrap = fetch(`${BASE}/api/v1/auth/csrf`, { credentials: "include" })
      .then(() => undefined)
      .catch(() => undefined)
      .finally(() => {
        csrfBootstrap = null;
      });
  }
  await csrfBootstrap;
}

async function request<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(init.headers as Record<string, string> | undefined) };
  const method = (init.method ?? "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD") await ensureCsrf();
  const token = csrfToken();
  if (token && method !== "GET" && method !== "HEAD") headers["X-CSRF-Token"] = token;

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, method, headers, credentials: "include" });
  } catch {
    throw new ApiError(0, "NETWORK", "Cannot reach Slotwise. Check your connection and try again.");
  }

  if (res.status === 204) return null as T;

  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const err = (body as { error?: { code?: string; message?: string; fieldErrors?: Record<string, string>; requestId?: string } } | null)?.error;
    throw new ApiError(
      res.status,
      err?.code ?? `HTTP_${res.status}`,
      messageForStatus(res.status, err?.code, err?.message),
      err?.fieldErrors ?? {},
      err?.requestId,
    );
  }
  return body as T;
}

// ---------------------------------------------------------------- auth

export type SessionUser = { id: string; email: string; role: string; emailVerified: boolean };

export async function register(email: string, password: string): Promise<{ id: string; email: string; emailVerified: boolean }> {
  return request("/api/v1/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
}
export async function login(email: string, password: string): Promise<SessionUser> {
  return request("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
}
export async function logout(): Promise<void> {
  await request("/api/v1/auth/logout", { method: "POST" });
}
export async function me(): Promise<SessionUser> {
  return request("/api/v1/auth/me");
}

// --------------------------------------------------------- event types

function mapEvent(e: Record<string, unknown>): EventType {
  return {
    id: String(e.id),
    title: String(e.title ?? ""),
    slug: String(e.slug ?? ""),
    description: String(e.description ?? ""),
    durationMinutes: Number(e.durationMinutes ?? 30),
    locationType: (e.locationType as EventType["locationType"]) ?? "online",
    locationDetails: String(e.locationDetails ?? ""),
    timezone: String(e.timezone ?? "UTC"),
    isPublished: Boolean(e.isPublished),
    archived: Boolean(e.archivedAt),
  };
}

export async function listEventTypes(): Promise<EventType[]> {
  const data = await request<Record<string, unknown>[]>("/api/v1/event-types");
  return data.map(mapEvent);
}

export async function getEventType(id: string): Promise<EventType | null> {
  try {
    const data = await request<Record<string, unknown>>(`/api/v1/event-types/${encodeURIComponent(id)}`);
    return mapEvent(data);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export async function createEventType(input: Partial<EventType>): Promise<EventType> {
  const data = await request<Record<string, unknown>>("/api/v1/event-types", {
    method: "POST",
    body: JSON.stringify({
      title: input.title ?? "New session",
      durationMinutes: input.durationMinutes ?? 30,
      locationType: input.locationType ?? "online",
      locationDetails: input.locationDetails,
      timezone: input.timezone ?? "Asia/Kolkata",
      description: input.description,
    }),
  });
  return mapEvent(data);
}

export async function updateEventType(id: string, input: Partial<EventType>): Promise<EventType> {
  const data = await request<Record<string, unknown>>(`/api/v1/event-types/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({
      title: input.title,
      description: input.description,
      durationMinutes: input.durationMinutes,
      locationType: input.locationType,
      locationDetails: input.locationDetails,
      timezone: input.timezone,
      isPublished: input.isPublished,
    }),
  });
  return mapEvent(data);
}

export async function archiveEventType(id: string): Promise<void> {
  await request(`/api/v1/event-types/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function publishEventType(id: string): Promise<EventType> {
  return updateEventType(id, { isPublished: true });
}

// -------------------------------------------------------- availability

function mapRule(r: Record<string, unknown>): AvailabilityRule {
  return {
    id: String(r.id),
    eventTypeId: String(r.eventTypeId),
    weekday: Number(r.weekday),
    startLocal: String(r.startLocal),
    endLocal: String(r.endLocal),
    timezone: String(r.timezone),
  };
}

export async function getAvailability(eventTypeId: string): Promise<AvailabilityRule[]> {
  const data = await request<Record<string, unknown>[]>(
    `/api/v1/event-types/${encodeURIComponent(eventTypeId)}/availability`,
  );
  return data.map(mapRule);
}

export async function setAvailability(eventTypeId: string, rules: AvailabilityRule[]): Promise<AvailabilityRule[]> {
  const data = await request<Record<string, unknown>[]>(
    `/api/v1/event-types/${encodeURIComponent(eventTypeId)}/availability`,
    {
      method: "PUT",
      body: JSON.stringify(
        rules.map((r) => ({ weekday: r.weekday, startLocal: r.startLocal, endLocal: r.endLocal, timezone: r.timezone })),
      ),
    },
  );
  return data.map(mapRule);
}

// ------------------------------------------------------- public / slots

export async function getEventTypeBySlug(slug: string): Promise<EventType | null> {
  try {
    const data = await request<Record<string, unknown>>(`/api/v1/public/${encodeURIComponent(slug)}`);
    return {
      id: String(data.slug),
      title: String(data.title ?? ""),
      slug: String(data.slug ?? slug),
      description: String(data.description ?? ""),
      durationMinutes: Number(data.durationMinutes ?? 30),
      locationType: (data.locationType as EventType["locationType"]) ?? "online",
      locationDetails: String(data.locationDetails ?? ""),
      timezone: String(data.timezone ?? "UTC"),
      isPublished: true,
      archived: false,
    };
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export async function getSlots(slug: string, from: string, to: string, tz: string): Promise<Slot[]> {
  const qs = new URLSearchParams({ from, to, tz });
  const data = await request<Slot[]>(`/api/v1/public/${encodeURIComponent(slug)}/slots?${qs.toString()}`);
  return data;
}

// -------------------------------------------------------------- bookings

function mapBooking(b: Record<string, unknown>, token?: string): Booking {
  const ev = (b.eventType ?? {}) as Record<string, unknown>;
  return {
    id: String(b.id),
    reference: String(b.id),
    eventSlug: String(ev.slug ?? ""),
    eventTitle: String(ev.title ?? ""),
    hostTimezone: String(ev.timezone ?? b.timezone ?? "UTC"),
    inviteeName: String(b.inviteeName ?? ""),
    inviteeEmail: String(b.inviteeEmail ?? ""),
    inviteeNote: b.inviteeNote ? String(b.inviteeNote) : undefined,
    startAt: String(b.startAt),
    endAt: String(b.endAt),
    displayTimezone: String(b.timezone ?? "UTC"),
    status: (b.status as Booking["status"]) ?? "confirmed",
    managementToken: token,
  };
}

export async function createBooking(
  slug: string,
  input: CreateBookingInput,
): Promise<Booking & { managementToken?: string; replayed?: boolean }> {
  const data = await request<{ reference: string; booking: Record<string, unknown>; managementToken: string | null; replayed?: boolean }>(
    `/api/v1/public/${encodeURIComponent(slug)}/bookings`,
    { method: "POST", body: JSON.stringify(input) },
  );
  const booking = mapBooking(data.booking, data.managementToken ?? undefined);
  return { ...booking, reference: data.reference, replayed: data.replayed };
}

export async function getBookingByReference(_reference: string): Promise<Booking | null> {
  // Public references are management tokens; without the token the API (by design)
  // reveals nothing. The confirmation screen receives the booking via router state.
  return null;
}

export async function getBookingByToken(token: string): Promise<Booking | null> {
  try {
    const data = await request<Record<string, unknown>>(`/api/v1/manage/${encodeURIComponent(token)}`);
    return mapBooking(data, token);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export async function cancelBooking(token: string): Promise<Booking> {
  const data = await request<Record<string, unknown>>(`/api/v1/manage/${encodeURIComponent(token)}/cancel`, {
    method: "POST",
  });
  return mapBooking(data, token);
}

export async function rescheduleBooking(token: string, newStartAt: string, timezone?: string): Promise<Booking> {
  const data = await request<Record<string, unknown>>(`/api/v1/manage/${encodeURIComponent(token)}/reschedule`, {
    method: "POST",
    body: JSON.stringify({ startAt: newStartAt, timezone }),
  });
  return mapBooking(data, token);
}

export async function listBookings(filter: { status?: string; from?: string; to?: string } = {}): Promise<Booking[]> {
  const qs = new URLSearchParams();
  if (filter.status) qs.set("status", filter.status);
  if (filter.from) qs.set("from", filter.from);
  if (filter.to) qs.set("to", filter.to);
  const data = await request<Record<string, unknown>[]>(`/api/v1/bookings${Array.from(qs).length ? `?${qs.toString()}` : ""}`);
  return data.map((b) => mapBooking(b));
}
