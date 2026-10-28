import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Button } from "../components/Button";
import { Dialog } from "../components/Dialog";
import { Alert } from "../components/Alert";
import { StatusBadge } from "../components/StatusBadge";
import { getBookingByToken, cancelBooking, rescheduleBooking, getSlots } from "../lib/mockApi";
import type { Booking, Slot } from "../lib/types";

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

  useEffect(() => {
    if (!token) return;
    getBookingByToken(token).then((b) => {
      if (!b) setInvalid(true);
      else {
        setBooking(b);
        setTz(b.hostTimezone);
      }
    });
  }, [token]);

  useEffect(() => {
    if (!rescheduling || !booking) return;
    const from = new Date(date + "T00:00:00Z").toISOString();
    const to = new Date(new Date(date + "T00:00:00Z").getTime() + 86400000).toISOString();
    getSlots(booking.eventSlug, from, to, tz).then(setSlots);
  }, [rescheduling, date, booking, tz]);

  if (invalid) {
    return (
      <Shell title="Booking unavailable" subtitle="This link is invalid or expired.">
        <Alert variant="error">Invalid or expired token. No booking details disclosed.</Alert>
      </Shell>
    );
  }
  if (!booking) return <Shell title="Loading…" />;

  async function handleCancel() {
    if (!token) return;
    await cancelBooking(token);
    setBooking({ ...booking!, status: "canceled" });
    setCancelOpen(false);
  }

  async function handleReschedule() {
    if (!token || !selected) return;
    setError(null);
    try {
      const updated = await rescheduleBooking(token, selected);
      setBooking(updated);
      setRescheduling(false);
      setSelected(null);
    } catch {
      setError("That time is no longer available. Choose another slot.");
    }
  }

  return (
    <Shell title="Manage booking" subtitle={booking.status === "canceled" ? "Canceled" : "Cancel or reschedule"}>
      <div className="flex flex-col gap-4">
        <p className="text-body text-text">{booking.eventTitle}</p>
        <p className="text-body text-text">
          {new Date(booking.startAt).toLocaleString(undefined, { timeZone: booking.displayTimezone })}{" "}
          {booking.displayTimezone}
        </p>
        <StatusBadge status={booking.status === "no_show" ? "no_show" : booking.status === "completed" ? "completed" : booking.status === "canceled" ? "canceled" : "confirmed"} />
        {booking.status === "confirmed" && (
          <div className="flex gap-2">
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
              New date
            </label>
            <input
              id="resched-date"
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="rounded-md border border-border-input px-3 py-2 text-body text-text"
            />
            <div className="grid grid-cols-2 gap-2">
              {slots.map((s) => (
                <button
                  key={s.startAt}
                  type="button"
                  onClick={() => setSelected(s.startAt)}
                  className={`rounded-md border px-3 py-2 text-small ${
                    selected === s.startAt ? "border-accent bg-accent text-on-accent" : "border-border bg-surface text-text"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
            {error && <Alert variant="error">{error}</Alert>}
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

