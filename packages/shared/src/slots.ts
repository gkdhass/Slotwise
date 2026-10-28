import { addMinutes, format } from "date-fns";
import { fromZonedTime, toZonedTime } from "date-fns-tz";

export type AvailabilityRule = {
  weekday: number; // 0-6 (in event timezone)
  startLocal: string; // HH:mm
  endLocal: string; // HH:mm
};

export type ExistingBooking = {
  startAt: string; // ISO UTC
  endAt: string; // ISO UTC
  status: string;
};

export type Slot = {
  startAt: string; // ISO UTC
  endAt: string; // ISO UTC
  label: string; // in display timezone
};

export type GenerateSlotsInput = {
  rules: AvailabilityRule[];
  durationMinutes: number;
  eventTimezone: string;
  displayTimezone: string;
  from: Date;
  to: Date;
  existingBookings: ExistingBooking[];
  now?: Date;
};

export function generateSlots(input: GenerateSlotsInput): Slot[] {
  const { rules, durationMinutes, eventTimezone, displayTimezone, from, to, existingBookings, now } = input;
  const confirmed = existingBookings.filter((b) => b.status === "confirmed");
  const slots: Slot[] = [];
  const seen = new Set<string>();

  // iterate day by day in event timezone
  const zonedStart = toZonedTime(from, eventTimezone);
  zonedStart.setHours(0, 0, 0, 0);
  const zonedEnd = toZonedTime(to, eventTimezone);
  let zonedDay = new Date(zonedStart);
  while (zonedDay < zonedEnd) {
    const wd = zonedDay.getDay();
    const dayRules = rules.filter((r) => r.weekday === wd);

    for (const rule of dayRules) {
      const [sh, sm] = rule.startLocal.split(":").map(Number);
      const [eh, em] = rule.endLocal.split(":").map(Number);

      const localStart = new Date(zonedDay);
      localStart.setHours(sh, sm, 0, 0);
      const localEnd = new Date(zonedDay);
      localEnd.setHours(eh, em, 0, 0);

      // handle overnight? assume same day
      const utcStart = fromZonedTime(localStart, eventTimezone);
      const utcEnd = fromZonedTime(localEnd, eventTimezone);

      let cursor = utcStart;
      while (addMinutes(cursor, durationMinutes) <= utcEnd) {
        const slotStart = cursor;
        const slotEnd = addMinutes(cursor, durationMinutes);
        if (slotStart >= from && slotEnd <= to) {
          if (!now || slotStart.getTime() >= now.getTime() - 60000) {
            const conflict = confirmed.some(
              (b) =>
                new Date(b.startAt).getTime() < slotEnd.getTime() &&
                new Date(b.endAt).getTime() > slotStart.getTime(),
            );
            if (!conflict && !seen.has(slotStart.toISOString())) {
              seen.add(slotStart.toISOString());
              slots.push({
                startAt: slotStart.toISOString(),
                endAt: slotEnd.toISOString(),
                label: format(toZonedTime(slotStart, displayTimezone), "EEE d MMM, h:mm a"),
              });
            }
          }
        }
        cursor = addMinutes(cursor, durationMinutes);
      }
    }

    // advance one day
    zonedDay = new Date(zonedDay);
    zonedDay.setDate(zonedDay.getDate() + 1);
  }

  return slots.sort((a, b) => a.startAt.localeCompare(b.startAt));
}