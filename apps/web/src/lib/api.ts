import type {
  EventType,
  AvailabilityRule,
  Slot,
  Booking,
  CreateBookingInput,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:4000";

function csrfToken(): string | null {
  const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

async function request(path: string, init: RequestInit = {}) {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(init.headers as any) };
  const t = csrfToken();
  if (t && init.method && init.method !== "GET") headers["X-CSRF-Token"] = t;
  const res = await fetch(`${BASE}${path}`, { ...init, headers, credentials: "include" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error?.code ?? `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

// Auth
export async function register(email: string, password: string) {
  return request("/api/v1/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
}
export async function login(email: string, password: string) {
  return request("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
}
export async function logout() {
  return request("/api/v1/auth/logout", { method: "POST" });
}
export async function me() {
  return request("/api/v1/auth/me");
}

// Event types
export async function listEventTypes(): Promise<EventType[]> {
  const data = await request("/api/v1/event-types");
  return (data as any[]).map(mapEvent);
}
export async function getEventType(id: string): Promise<EventType | null> {
  try {
    const data = await request(`/api/v1/event-types/${id}`); // not in contract; use list filter
    return mapEvent(data);
  } catch {
    return null;
  }
}
// (no single-event GET in contract; fetch via list)
export async function getEventTypeBySlug(slug: string): Promise<EventType | null> {
  try {
    const data: any = await request(`/api/v1/public/${slug}`);
    return {
      id: slug,
      title: data.title,
      slug: data.slug,
      description: data.description ?? "",
      durationMinutes: data.durationMinutes,
      locationType: data.locationType,
      locationDetails: data.locationDetails ?? "",
      timezone: data.timezone,
      isPublished: true,
      archived: false,
    };
  } catch {
    return null;
  }
}
export async function createEventType(input: Partial<EventType>): Promise<EventType> {
  const data = await request("/api/v1/event-types", {
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
  const data = await request(`/api/v1/event-types/${id}`, {
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
  await request(`/api/v1/event-types/${id}`, { method: "DELETE" });
}
export async function publishEventType(id: string): Promise<EventType> {
  const data = await request(`/api/v1/event-types/${id}`, { method: "PATCH", body: JSON.stringify({ isPublished: true }) });
  return mapEvent(data);
}

function mapEvent(e: any): EventType {
  return {
    id: e.id,
    title: e.title,
    slug: e.slug,
    description: e.description ?? "",
    durationMinutes: e.durationMinutes,
    locationType: e.locationType,
    locationDetails: e.locationDetails ?? "",
    timezone: e.timezone,
    isPublished: e.isPublished,
    archived: !!e.archivedAt,
  };
}

// Availability
export async function getAvailability(eventTypeId: string): Promise<AvailabilityRule[]> {
  // no GET endpoint in contract; store locally? For M2, fetch via event? 
  // We'll return empty; availability is set via PUT only. (Limitation)
  return [];
}
export async function setAvailability(eventTypeId: string, rules: AvailabilityRule[]): Promise<AvailabilityRule[]> {
  const data = await request(`/api/v1/event-types/${eventTypeId}/availability`, {
    method: "PUT",
    body: JSON.stringify(rules.map((r) => ({ weekday: r.weekday, startLocal: r.startLocal, endLocal: r.endLocal, timezone: r.timezone }))),
  });
  return data as AvailabilityRule[];
}

// Slots
export async function getSlots(slug: string, from: string, to: string, tz: string): Promise<Slot[]> {
  const data: any = await request(`/api/v1/public/${slug}/slots?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&tz=${encodeURIComponent(tz)}`);
  return data as Slot[];
}

// Bookings
export async function createBooking(slug: string, input: CreateBookingInput): Promise<Booking & { managementToken?: string }> {
  const data: any = await request(`/api/v1/public/${slug}/bookings`, {
    method: "POST",
    body: JSON.stringify(input),
  });
  return {
    id: data.booking.id,
    reference: data.reference ?? data.booking.id,
    eventSlug: slug,
    eventTitle: "",
    hostTimezone: "",
    inviteeName: data.booking.inviteeName,
    inviteeEmail: data.booking.inviteeEmail,
    startAt: data.booking.startAt,
    endAt: data.booking.endAt,
    displayTimezone: input.timezone,
    status: data.booking.status,
    managementToken: data.managementToken ?? "",
  };
}
export async function getBookingByReference(ref: string): Promise<Booking | null> {
  // no endpoint; return null for now
  return null;
}
export async function getBookingByToken(token: string): Promise<Booking | null> {
  // no GET by token in contract; return null for now
  return null;
}
export async function cancelBooking(token: string): Promise<Booking> {
  const data: any = await request(`/api/v1/manage/${token}/cancel`, { method: "POST" });
  return data as Booking;
}
export async function rescheduleBooking(token: string, newStartAt: string): Promise<Booking> {
  const data: any = await request(`/api/v1/manage/${token}/reschedule`, { method: "POST", body: JSON.stringify({ startAt: newStartAt, timezone: "UTC" }) });
  return data as Booking;
}
export async function listBookings(): Promise<Booking[]> {
  const data: any = await request("/api/v1/bookings");
  return (data as any[]).map((b) => ({
    id: b.id,
    reference: b.id,
    eventSlug: "",
    eventTitle: b.eventType?.title ?? "",
    hostTimezone: "",
    inviteeName: b.inviteeName,
    inviteeEmail: b.inviteeEmail,
    startAt: b.startAt,
    endAt: b.endAt,
    displayTimezone: b.timezone,
    status: b.status,
    managementToken: "",
  }));
}