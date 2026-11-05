import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Button } from "../components/Button";
import { StatusBadge } from "../components/StatusBadge";
import { Alert } from "../components/Alert";
import { ApiError, getEventType, publishEventType } from "../lib/api";
import { CANCELLATION_POLICY } from "../lib/policy";
import type { EventType } from "../lib/types";

export default function S05PreviewPublish() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [ev, setEv] = useState<EventType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);

  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        const e = await getEventType(id);
        if (!e) setError("We could not find that session.");
        setEv(e);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          navigate("/login");
          return;
        }
        setError(err instanceof ApiError ? err.userMessage : "Could not load this session.");
      }
    })();
  }, [id, navigate]);

  async function handlePublish() {
    if (!id) return;
    setPublishing(true);
    setError(null);
    try {
      setEv(await publishEventType(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.userMessage : "Could not publish this session.");
    } finally {
      setPublishing(false);
    }
  }

  if (!ev) return <Shell title="Preview and publish" subtitle={error ?? "Loading…"} />;

  const publicUrl = `${window.location.origin}/book/${ev.slug}`;

  return (
    <Shell title="Preview and publish" subtitle="Review your booking page">
      <div className="flex flex-col gap-4">
        {error && <Alert variant="error">{error}</Alert>}
        <div className="rounded-md border border-border p-4">
          <p className="text-body font-medium text-text">{ev.title}</p>
          <p className="text-small text-text-muted">
            {ev.durationMinutes} minutes • {ev.locationType} • times shown in {ev.timezone}
          </p>
          <div className="mt-2">
            <StatusBadge status={ev.isPublished ? "published" : "draft"} />
          </div>
          {ev.description && <p className="mt-2 text-small text-text-muted">{ev.description}</p>}
        </div>
        <div className="rounded-md border border-border bg-bg p-3" data-testid="policy-preview">
          <p className="text-small font-medium text-text">Cancellation policy (invitees will see this)</p>
          <p className="mt-1 text-small text-text-muted">{CANCELLATION_POLICY}</p>
        </div>
        {ev.isPublished && (
          <p className="text-small text-text-muted">
            Public link: <span className="text-text">{publicUrl}</span>
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button onClick={handlePublish} loading={publishing} disabled={ev.isPublished}>
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
