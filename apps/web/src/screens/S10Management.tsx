import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Button } from "../components/Button";
import { Dialog } from "../components/Dialog";
import { Alert } from "../components/Alert";
import { StatusBadge } from "../components/StatusBadge";
import { ApiError, getBookingByToken, cancelBooking, rescheduleBooking, getSlots } from "../lib/api";
import type { Booking, Slot } from "../lib/types";
import { MAX_SLOT_RANGE_DAYS } from "@slotwise/shared";

function dateInZone(iso: string, tz: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(
    new Date(iso),
  );
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

export default function S10Management() {
  const { token } = useParams();
  const [booking, setBooking] = useState<Booking | null>(null);
  const [invalid, setInvalid] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [rescheduling, setRescheduling] = useState(false);
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [slots, setSlots] = useState<Slot[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [tz, setTz] = useState("Asia/Kolkata");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        const b = await getBookingByToken(token);
        if (!b) setInvalid(true);
        else {
          setBooking(b);
          setTz(b.displayTimezone);
          // Default the reschedule date to the booking's own date, computed in
          // the zone the slot list is filtered by.
          setDate(dateInZone(b.startAt, b.displayTimezone));
        }
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) setInvalid(true);
        else setError(err instanceof ApiError ? err.userMessage : "Could not load this booking.");
      }
    })();
  }, [token]);

  const loadSlots = useCallback(async () => {
    if (!booking?.eventSlug) return;
    setError(null);
    try {
      const base = new Date(`${date}T00:00:00Z`).getTime();
      // 3-day window, clamped to the API's documented maximum (MAX_SLOT_RANGE_DAYS).
      const to = new Date(Math.min(base + 2 * 86_400_000, base + MAX_SLOT_RANGE_DAYS * 86_400_000)).toISOString();
      const all = await getSlots(booking.eventSlug, new Date(base - 86_400_000).toISOString(), to, tz);
      setSlots(all.filter((s) => dateInZone(s.startAt, tz) === date));
    } catch (err) {
      setError(err instanceof ApiError ? err.userMessage : "Could not load times.");
    }
  }, [booking?.eventSlug, date, tz]);

  useEffect(() => {
    if (rescheduling) loadSlots();
  }, [rescheduling, loadSlots]);

  async function handleCancel() {
    if (!token) return;
    setError(null);
    try {
      const updated = await cancelBooking(token);
      setBooking(updated);
      setCancelOpen(false);
      setNotice("Booking canceled. The time slot is now free.");
    } catch (err) {
      setCancelOpen(false);
      setError(err instanceof ApiError ? err.userMessage : "Could not cancel this booking.");
    }
  }

  async function handleReschedule() {
    if (!token || !selected) return;
    setError(null);
    setNotice(null);
    try {
      const updated = await rescheduleBooking(token, selected, tz);
      setBooking(updated);
      setRescheduling(false);
      setSelected(null);
      setNotice("Booking rescheduled.");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.userMessage);
        // Refresh the list so the taken slot disappears.
        loadSlots();
      } else {
        setError("Could not reschedule this booking.");
      }
    }
  }

  if (invalid) {
    return (
      <Shell title="Booking unavailable" subtitle="This link is invalid or expired.">
        <Alert variant="error">This management link is invalid or expired.</Alert>
      </Shell>
    );
  }
  if (!booking) return <Shell title="Loading…" subtitle={error ?? "Fetching your booking"} />;

  return (
    <Shell title="Manage booking" subtitle={booking.status === "canceled" ? "Canceled" : "Cancel or reschedule"}>
      <div className="flex flex-col gap-4">
        {error && <Alert variant="error">{error}</Alert>}
        {notice && <Alert variant="success">{notice}</Alert>}
        <p className="text-body text-text">{booking.eventTitle}</p>
        <div>
          <p className="text-body text-text">
            {new Date(booking.startAt).toLocaleString(undefined, {
              timeZone: booking.displayTimezone,
              dateStyle: "full",
              timeStyle: "short",
            })}
          </p>
          <p className="text-small text-text-muted">Time zone: {booking.displayTimezone}</p>
          {booking.hostTimezone && booking.hostTimezone !== booking.displayTimezone && (
            <p className="text-small text-text-muted">
              Host time zone:{" "}
              {new Date(booking.startAt).toLocaleString(undefined, {
                timeZone: booking.hostTimezone,
                dateStyle: "full",
                timeStyle: "short",
              })}{" "}
              ({booking.hostTimezone})
            </p>
          )}
        </div>
        <StatusBadge
          status={
            booking.status === "no_show"
              ? "no_show"
              : booking.status === "completed"
                ? "completed"
                : booking.status === "canceled"
                  ? "canceled"
                  : "confirmed"
          }
        />
        {booking.status === "confirmed" && (
          <div className="flex flex-wrap gap-2">
            <Button variant="danger" onClick={() => setCancelOpen(true)}>
              Cancel
            </Button>
            <Button variant="secondary" onClick={() => setRescheduling((v) => !v)}>
              {rescheduling ? "Hide" : "Reschedule"}
            </Button>
          </div>
        )}
        {rescheduling && (
          <div className="flex flex-col gap-3 rounded-md border border-border p-3">
            <label htmlFor="resched-date" className="text-small font-medium text-text">
              New date (times in {tz})
            </label>
            <input
              id="resched-date"
              type="date"
              value={date}
              onChange={(e) => {
                setDate(e.target.value);
                setSelected(null);
              }}
              className="rounded-md border border-border-input px-3 py-2 text-body text-text"
            />
            {slots.length === 0 && <p className="text-small text-text-muted">No times are open for this date.</p>}
            <div className="grid grid-cols-2 gap-2">
              {slots.map((s) => (
                <button
                  key={s.startAt}
                  type="button"
                  onClick={() => setSelected(s.startAt)}
                  aria-pressed={selected === s.startAt}
                  className={`rounded-md border px-3 py-2 text-small ${
                    selected === s.startAt ? "border-accent bg-accent text-on-accent" : "border-border bg-surface text-text"
                  }`}
                >
                  {s.label}
                  <span className="block text-caption opacity-80">{tz}</span>
                </button>
              ))}
            </div>
            <Button onClick={handleReschedule} disabled={!selected}>
              Confirm reschedule
            </Button>
          </div>
        )}
        <Dialog open={cancelOpen} onClose={() => setCancelOpen(false)} title="Cancel booking?">
          <p className="text-body text-text-muted">This will release the time slot.</p>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setCancelOpen(false)}>
              Keep
            </Button>
            <Button variant="danger" onClick={handleCancel}>
              Cancel booking
            </Button>
          </div>
        </Dialog>
      </div>
    </Shell>
  );
}
