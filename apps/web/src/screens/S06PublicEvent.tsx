import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";
import { ApiError, getEventTypeBySlug } from "../lib/api";
import { CANCELLATION_POLICY } from "../lib/policy";
import type { EventType } from "../lib/types";

export default function S06PublicEvent() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const [ev, setEv] = useState<EventType | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    (async () => {
      try {
        const e = await getEventTypeBySlug(slug);
        if (!e || !e.isPublished || e.archived) setNotFound(true);
        else setEv(e);
      } catch (err) {
        setError(err instanceof ApiError ? err.userMessage : "Could not load this booking page.");
      }
    })();
  }, [slug]);

  if (notFound) {
    return (
      <Shell title="Unavailable" subtitle="This booking page is not available.">
        <p className="text-text-muted">The event may be unpublished, archived, or not found.</p>
      </Shell>
    );
  }
  if (error) {
    return (
      <Shell title="Unavailable" subtitle="This booking page is not available.">
        <Alert variant="error">{error}</Alert>
      </Shell>
    );
  }
  if (!ev) return <Shell title="Loading…" />;

  return (
    <Shell title={ev.title} subtitle={`${ev.durationMinutes} minutes • ${ev.locationType}`}>
      <div className="flex flex-col gap-4">
        {ev.description && <p className="text-body text-text-muted">{ev.description}</p>}
        <p className="text-small text-text-muted">Location: {ev.locationDetails || ev.locationType}</p>
        <p className="text-small text-text-muted">Times are shown in {ev.timezone}.</p>
        <div className="rounded-md border border-border bg-bg p-3" data-testid="policy-public">
          <p className="text-small font-medium text-text">Cancellation policy</p>
          <p className="mt-1 text-small text-text-muted">{CANCELLATION_POLICY}</p>
        </div>
        <Button onClick={() => navigate(`/book/${ev.slug}/slots`)}>Choose a time</Button>
      </div>
    </Shell>
  );
}
