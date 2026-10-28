import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Button } from "../components/Button";
import { StatusBadge } from "../components/StatusBadge";
import { Alert } from "../components/Alert";
import { ApiError, listEventTypes, createEventType } from "../lib/api";
import type { EventType } from "../lib/types";

export default function S02Dashboard() {
  const [events, setEvents] = useState<EventType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setEvents(await listEventTypes());
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        navigate("/login");
        return;
      }
      setError(e instanceof ApiError ? e.userMessage : "Could not load your sessions.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleCreate() {
    setError(null);
    try {
      const ev = await createEventType({ title: "New session", timezone: "Asia/Kolkata" });
      navigate(`/app/events/${ev.id}/edit`);
    } catch (e) {
      setError(e instanceof ApiError ? e.userMessage : "Could not create a session.");
    }
  }

  return (
    <Shell title="Dashboard" subtitle="Manage your event types and appointments">
      <div className="flex items-center justify-between">
        <p className="text-body text-text-muted">Your event types</p>
        <Button onClick={handleCreate}>Set up a session</Button>
      </div>
      {error && (
        <div className="mt-4">
          <Alert variant="error">{error}</Alert>
        </div>
      )}
      {loading && <p className="mt-4 text-text-muted">Loading…</p>}
      {!loading && events.length === 0 && !error && (
        <p className="mt-4 text-text-muted">No sessions yet. Create your first one.</p>
      )}
      <ul className="mt-4 flex flex-col gap-3">
        {events.map((e) => (
          <li key={e.id} className="flex flex-col gap-3 rounded-md border border-border p-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-body font-medium text-text">{e.title}</p>
              <p className="text-small text-text-muted">
                {e.durationMinutes} minutes • {e.timezone}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={e.isPublished ? "published" : "draft"} />
              <Button variant="secondary" onClick={() => navigate(`/app/events/${e.id}/edit`)}>
                Edit
              </Button>
              <Button variant="ghost" onClick={() => navigate(`/app/events/${e.id}/availability`)}>
                Availability
              </Button>
              <Button variant="ghost" onClick={() => navigate(`/app/events/${e.id}/preview`)}>
                Preview
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <div className="mt-6">
        <Button variant="secondary" onClick={() => navigate("/app/bookings")}>
          View bookings
        </Button>
      </div>
    </Shell>
  );
}
