import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Button } from "../components/Button";
import { StatusBadge } from "../components/StatusBadge";
import { getEventType, publishEventType } from "../lib/mockApi";
import type { EventType } from "../lib/types";

export default function S05PreviewPublish() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [ev, setEv] = useState<EventType | null>(null);

  useEffect(() => {
    if (!id) return;
    getEventType(id).then(setEv);
  }, [id]);

  async function handlePublish() {
    if (!id) return;
    const updated = await publishEventType(id);
    setEv(updated);
  }

  if (!ev) return <Shell title="Preview and publish" subtitle="Loading…" />;

  return (
    <Shell title="Preview and publish" subtitle="Review your booking page">
      <div className="flex flex-col gap-4">
        <div className="rounded-md border border-border p-4">
          <p className="text-body font-medium text-text">{ev.title}</p>
          <p className="text-small text-text-muted">
            {ev.durationMinutes} minutes • {ev.locationType} • {ev.timezone}
          </p>
          <div className="mt-2">
            <StatusBadge status={ev.isPublished ? "published" : "draft"} />
          </div>
          {ev.description && <p className="mt-2 text-small text-text-muted">{ev.description}</p>}
        </div>
        <div className="flex gap-2">
          <Button onClick={handlePublish} disabled={ev.isPublished}>
            {ev.isPublished ? "Published" : "Publish booking page"}
          </Button>
          <Button variant="secondary" onClick={() => navigate(`/book/${ev.slug}`)}>
            View public page
          </Button>
        </div>
      </div>
    </Shell>
  );
}