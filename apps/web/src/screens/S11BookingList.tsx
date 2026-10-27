import { useEffect, useState } from "react";
import { Shell } from "../components/Shell";
import { StatusBadge } from "../components/StatusBadge";
import { listBookings } from "../lib/mockApi";
import type { Booking } from "../lib/types";

export default function S11BookingList() {
  const [bookings, setBookings] = useState<Booking[]>([]);
  useEffect(() => {
    listBookings().then(setBookings);
  }, []);

  return (
    <Shell title="Bookings" subtitle="Your appointments">
      {bookings.length === 0 && <p className="text-text-muted">No bookings yet.</p>}
      <ul className="flex flex-col gap-3">
        {bookings.map((b) => (
          <li key={b.id} className="flex items-center justify-between rounded-md border border-border p-3">
            <div>
              <p className="text-body font-medium text-text">{b.inviteeName}</p>
              <p className="text-small text-text-muted">
                {b.eventTitle} • {new Date(b.startAt).toLocaleString(undefined, { timeZone: b.displayTimezone })}
              </p>
            </div>
            <StatusBadge
              status={
                b.status === "canceled"
                  ? "canceled"
                  : b.status === "completed"
                    ? "completed"
                    : b.status === "no_show"
                      ? "no_show"
                      : "confirmed"
              }
            />
          </li>
        ))}
      </ul>
    </Shell>
  );
}