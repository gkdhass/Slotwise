export type EventType = {
  id: string;
  title: string;
  slug: string;
  description: string;
  durationMinutes: number;
  locationType: "custom" | "phone" | "online";
  locationDetails: string;
  timezone: string;
  isPublished: boolean;
  archived: boolean;
};

export type AvailabilityRule = {
  id: string;
  eventTypeId: string;
  weekday: number; // 0-6
  startLocal: string; // HH:mm
  endLocal: string; // HH:mm
  timezone: string;
};

export type Slot = {
  startAt: string; // ISO UTC
  endAt: string; // ISO UTC
  label: string;
};

export type Booking = {
  id: string;
  reference: string;
  eventSlug: string;
  eventTitle: string;
  hostTimezone: string;
  inviteeName: string;
  inviteeEmail: string;
  inviteeNote?: string;
  startAt: string;
  endAt: string;
  displayTimezone: string;
  status: "confirmed" | "canceled" | "completed" | "no_show";
  managementToken?: string;
};

export type CreateBookingInput = {
  startAt: string;
  timezone: string;
  invitee: { name: string; email: string; note?: string };
  idempotencyKey: string;
};