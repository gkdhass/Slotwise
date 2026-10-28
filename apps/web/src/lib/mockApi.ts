import { addMinutes } from "date-fns";
import { generateSlots } from "@slotwise/shared";
import type {
  EventType,
  AvailabilityRule,
  Slot,
  Booking,
  CreateBookingInput,
} from "./types";

const STORAGE_KEY = "slotwise-mock-state";

type State = {
  events: EventType[];
  availability: AvailabilityRule[];
  bookings: Booking[];
};

function seedState(): State {
  const ev: EventType = {
    id: "ev-1",
    title: "Intro tutoring",
    slug: "intro-tutoring",
    description: "A 30-minute intro session.",
    durationMinutes: 30,
    locationType: "online",
    locationDetails: "Video call link sent after booking",
    timezone: "Asia/Kolkata",
    isPublished: true,
    archived: false,
  };
  const rules: AvailabilityRule[] = [1, 2, 3, 4, 5].map((wd) => ({
    id: `ar-${wd}`,
    eventTypeId: ev.id,
    weekday: wd,
    startLocal: "10:00",
    endLocal: "17:00",
    timezone: ev.timezone,
  }));
  return { events: [ev], availability: rules, bookings: [] };
}

function loadState(): State {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as State;
  } catch {
    /* ignore */
  }
  const s = seedState();
  saveState(s);
  return s;
}

function saveState(s: State) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

let state: State = loadState();

function uid(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 9)}`;
}

function slugify(title: string) {
  return title
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

// ---------- Event types ----------
export async function listEventTypes(): Promise<EventType[]> {
  return [...state.events];
}

export async function getEventType(id: string): Promise<EventType | null> {
  return state.events.find((e) => e.id === id) ?? null;
}

export async function getEventTypeBySlug(slug: string): Promise<EventType | null> {
  return state.events.find((e) => e.slug === slug) ?? null;
}

export async function createEventType(input: Partial<EventType>): Promise<EventType> {
  const title = input.title ?? "New session";
  const ev: EventType = {
    id: uid("ev"),
    title,
    slug: slugify(title) + "-" + Math.random().toString(36).slice(2, 5),
    description: input.description ?? "",
    durationMinutes: input.durationMinutes ?? 30,
    locationType: input.locationType ?? "online",
    locationDetails: input.locationDetails ?? "",
    timezone: input.timezone ?? "Asia/Kolkata",
    isPublished: false,
    archived: false,
  };
  state.events.push(ev);
  saveState(state);
  return ev;
}

export async function updateEventType(id: string, input: Partial<EventType>): Promise<EventType> {
  const ev = state.events.find((e) => e.id === id);
  if (!ev) throw new Error("not found");
  Object.assign(ev, input);
  if (input.title) ev.slug = slugify(input.title);
  saveState(state);
  return ev;
}

export async function archiveEventType(id: string): Promise<void> {
  const ev = state.events.find((e) => e.id === id);
  if (ev) {
    ev.archived = true;
    ev.isPublished = false;
    saveState(state);
  }
}

export async function publishEventType(id: string): Promise<EventType> {
  const ev = state.events.find((e) => e.id === id);
  if (!ev) throw new Error("not found");
  ev.isPublished = true;
  saveState(state);
  return ev;
}

// ---------- Availability ----------
export async function getAvailability(eventTypeId: string): Promise<AvailabilityRule[]> {
  return state.availability.filter((a) => a.eventTypeId === eventTypeId);
}

export async function setAvailability(eventTypeId: string, rules: AvailabilityRule[]): Promise<AvailabilityRule[]> {
  state.availability = state.availability.filter((a) => a.eventTypeId !== eventTypeId).concat(rules);
  saveState(state);
  return state.availability.filter((a) => a.eventTypeId === eventTypeId);
}

// ---------- Slots ----------
export async function getSlots(slug: string, from: string, to: string, tz: string): Promise<Slot[]> {
  const ev = state.events.find((e) => e.slug === slug);
  if (!ev || !ev.isPublished || ev.archived) return [];
  const rules = state.availability.filter((a) => a.eventTypeId === ev.id);
  const bookings = state.bookings.filter((b) => b.eventSlug === slug && b.status === "confirmed");
  const sharedRules = rules.map((r) => ({ weekday: r.weekday, startLocal: r.startLocal, endLocal: r.endLocal }));
  return generateSlots({
    rules: sharedRules,
    durationMinutes: ev.durationMinutes,
    eventTimezone: ev.timezone,
    displayTimezone: tz,
    from: new Date(from),
    to: new Date(to),
    existingBookings: bookings.map((b) => ({ startAt: b.startAt, endAt: b.endAt, status: b.status })),
    now: new Date(),
  });
}

// ---------- Bookings ----------
export async function createBooking(slug: string, input: CreateBookingInput): Promise<Booking> {
  const ev = state.events.find((e) => e.slug === slug);
  if (!ev || !ev.isPublished || ev.archived) throw new Error("unavailable");
  // idempotency via side map
  const idemMap = (state as unknown as { idem: Record<string, string> }).idem ?? {};
  (state as unknown as { idem: Record<string, string> }).idem = idemMap;
  if (idemMap[input.idempotencyKey]) {
    const b = state.bookings.find((x) => x.id === idemMap[input.idempotencyKey]);
    if (b) return b;
  }
  // validate slot not taken
  const conflict = state.bookings.some(
    (b) =>
      b.eventSlug === slug &&
      b.status === "confirmed" &&
      new Date(b.startAt).getTime() < new Date(input.startAt).getTime() + ev.durationMinutes * 60000 &&
      new Date(b.endAt).getTime() > new Date(input.startAt).getTime(),
  );
  if (conflict) throw new Error("SLOT_UNAVAILABLE");
  const start = new Date(input.startAt);
  const end = addMinutes(start, ev.durationMinutes);
  const booking: Booking = {
    id: uid("bk"),
    reference: `ref-${Math.random().toString(36).slice(2, 8)}`,
    eventSlug: slug,
    eventTitle: ev.title,
    hostTimezone: ev.timezone,
    inviteeName: input.invitee.name,
    inviteeEmail: input.invitee.email,
    inviteeNote: input.invitee.note,
    startAt: start.toISOString(),
    endAt: end.toISOString(),
    displayTimezone: input.timezone,
    status: "confirmed",
    managementToken: uid("mt"),
  };
  state.bookings.push(booking);
  idemMap[input.idempotencyKey] = booking.id;
  saveState(state);
  return booking;
}

export async function getBookingByReference(ref: string): Promise<Booking | null> {
  return state.bookings.find((b) => b.reference === ref) ?? null;
}

export async function getBookingByToken(token: string): Promise<Booking | null> {
  return state.bookings.find((b) => b.managementToken === token) ?? null;
}

export async function cancelBooking(token: string): Promise<Booking> {
  const b = state.bookings.find((x) => x.managementToken === token);
  if (!b) throw new Error("invalid token");
  b.status = "canceled";
  saveState(state);
  return b;
}

export async function rescheduleBooking(token: string, newStartAt: string): Promise<Booking> {
  const b = state.bookings.find((x) => x.managementToken === token);
  if (!b) throw new Error("invalid token");
  const ev = state.events.find((e) => e.slug === b.eventSlug);
  if (!ev) throw new Error("event not found");
  // check conflict
  const conflict = state.bookings.some(
    (x) =>
      x.eventSlug === b.eventSlug &&
      x.status === "confirmed" &&
      x.id !== b.id &&
      new Date(x.startAt).getTime() < new Date(newStartAt).getTime() + ev.durationMinutes * 60000 &&
      new Date(x.endAt).getTime() > new Date(newStartAt).getTime(),
  );
  if (conflict) throw new Error("SLOT_UNAVAILABLE");
  // reserve new first, then release old: in mock, update in place
  b.startAt = new Date(newStartAt).toISOString();
  b.endAt = addMinutes(new Date(newStartAt), ev.durationMinutes).toISOString();
  saveState(state);
  return b;
}

export async function listBookings(): Promise<Booking[]> {
  return [...state.bookings];
}

export function resetMockState() {
  state = seedState();
  saveState(state);
}