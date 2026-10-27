import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Button } from "../components/Button";
import { StatusBadge } from "../components/StatusBadge";
import { listEventTypes, createEventType } from "../lib/mockApi";
import type { EventType } from "../lib/types";

export default function S02Dashboard() {
  const [events, setEvents] = useState<EventType[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  async function refresh() {
    setLoading(true);
    setEvents(await listEventTypes());
    setLoading(false);
  }
  useEffect(() => {
    refresh();
  }, []);

  async function handleCreate() {
    const ev = await createEventType({ title: "New session", timezone: "Asia/Kolkata" });
    navigate(`/app/events/${ev.id}/edit`);
  }

  return (
    <Shell title="Dashboard" subtitle="Manage your event types and appointments">
      <div className="flex items-center justify-between">
        <p className="text-body text-text-muted">Your event types</p>
        <Button onClick={handleCreate}>Set up a session</Button>
      </div>
      {loading && <p className="mt-4 text-text-muted">Loading…</p>}
      {!loading && events.length === 0 && (
        <p className="mt-4 text-text-muted">No sessions yet. Create your first one.</p>
      )}
      <ul className="mt-4 flex flex-col gap-3">
        {events.map((e) => (
          <li key={e.id} className="flex items-center justify-between rounded-md border border-border p-3">
            <div>
              <p className="text-body font-medium text-text">{e.title}</p>
              <p className="text-small text-text-muted">
                {e.durationMinutes} minutes • {e.timezone}
              </p>
            </div>
            <div className="flex items-center gap-2">
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