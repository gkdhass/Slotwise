import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { StatusBadge } from "../components/StatusBadge";
import { Alert } from "../components/Alert";
import { ApiError, listBookings } from "../lib/api";
import type { Booking } from "../lib/types";

const STATUSES = [
  { value: "", label: "All statuses" },
  { value: "confirmed", label: "Confirmed" },
  { value: "canceled", label: "Canceled" },
  { value: "completed", label: "Completed" },
  { value: "no_show", label: "No show" },
];

export default function S11BookingList() {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [status, setStatus] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listBookings({
        status: status || undefined,
        from: from ? new Date(`${from}T00:00:00Z`).toISOString() : undefined,
        to: to ? new Date(`${to}T23:59:59Z`).toISOString() : undefined,
      });
      setBookings(data);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        navigate("/login");
        return;
      }
      setError(e instanceof ApiError ? e.userMessage : "Could not load bookings.");
    } finally {
      setLoading(false);
    }
  }, [status, from, to, navigate]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Shell title="Bookings" subtitle="Your appointments">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-status" className="text-small font-medium text-text">
            Status
          </label>
          <select
            id="filter-status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded-md border border-border-input px-3 py-2 text-body text-text"
          >
            {STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-from" className="text-small font-medium text-text">
            From
          </label>
          <input
            id="filter-from"
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            className="rounded-md border border-border-input px-3 py-2 text-body text-text"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-to" className="text-small font-medium text-text">
            To
          </label>
          <input
            id="filter-to"
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className="rounded-md border border-border-input px-3 py-2 text-body text-text"
          />
        </div>
      </div>

      {error && (
        <div className="mt-4">
          <Alert variant="error">{error}</Alert>
        </div>
      )}
      {loading && <p className="mt-4 text-text-muted">Loading…</p>}
      {!loading && bookings.length === 0 && !error && <p className="mt-4 text-text-muted">No bookings match these filters.</p>}
      <ul className="mt-4 flex flex-col gap-3">
        {bookings.map((b) => (
          <li key={b.id} className="flex flex-col gap-2 rounded-md border border-border p-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-body font-medium text-text">{b.inviteeName}</p>
              <p className="text-small text-text-muted">
                {b.eventTitle} • {new Date(b.startAt).toLocaleString(undefined, { timeZone: b.displayTimezone })}{" "}
                {b.displayTimezone}
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
