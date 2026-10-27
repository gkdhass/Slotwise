import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Button } from "../components/Button";
import { getEventTypeBySlug } from "../lib/mockApi";
import type { EventType } from "../lib/types";

export default function S06PublicEvent() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const [ev, setEv] = useState<EventType | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!slug) return;
    (async () => {
      const e = await getEventTypeBySlug(slug);
      if (!e || !e.isPublished || e.archived) setNotFound(true);
      else setEv(e);
    })();
  }, [slug]);

  if (notFound) {
    return (
      <Shell title="Unavailable" subtitle="This booking page is not available.">
        <p className="text-text-muted">The event may be unpublished, archived, or not found.</p>
      </Shell>
    );
  }
  if (!ev) return <Shell title="Loading…" />;

  return (
    <Shell title={ev.title} subtitle={`${ev.durationMinutes} minutes • ${ev.locationType} • ${ev.timezone}`}>
      <div className="flex flex-col gap-4">
        {ev.description && <p className="text-body text-text-muted">{ev.description}</p>}
        <p className="text-small text-text-muted">Location: {ev.locationDetails || ev.locationType}</p>
        <Button onClick={() => navigate(`/book/${ev.slug}/slots`)}>Choose a time</Button>
      </div>
    </Shell>
  );
}