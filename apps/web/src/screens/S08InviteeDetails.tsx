import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams, useNavigate, useLocation } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Input } from "../components/Input";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";
import { ApiError, createBooking, getEventTypeBySlug } from "../lib/api";
import type { EventType } from "../lib/types";

type InviteeDraft = { name: string; email: string; note: string };

function newIdempotencyKey(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `key-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
}

export default function S08InviteeDetails() {
  const { slug } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const draft = ((location.state as { invitee?: InviteeDraft } | null)?.invitee ?? {}) as Partial<InviteeDraft>;

  const startAt = params.get("start") ?? "";
  const [name, setName] = useState(draft.name ?? "");
  const [email, setEmail] = useState(draft.email ?? "");
  const [note, setNote] = useState(draft.note ?? "");
  const [errors, setErrors] = useState<{ name?: string; email?: string }>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ev, setEv] = useState<EventType | null>(null);

  // One key per form instance: retries of the same submission are idempotent.
  const idempotencyKey = useMemo(() => newIdempotencyKey(), []);

  useEffect(() => {
    if (!slug) return;
    getEventTypeBySlug(slug)
      .then(setEv)
      .catch(() => {
        /* the booking call will surface the real error */
      });
  }, [slug]);

  function validate() {
    const e: typeof errors = {};
    if (!name.trim()) e.name = "Name is required";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) e.email = "Enter a valid email";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;
    setSubmitting(true);
    setError(null);
    try {
      const booking = await createBooking(slug!, {
        startAt,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        invitee: { name, email, note },
        idempotencyKey,
      });
      // Only reached after the server confirmed the booking.
      navigate(`/booking/confirmed/${booking.reference}`, { state: { booking } });
    } catch (err) {
      if (err instanceof ApiError && (err.status === 409 || err.code === "SLOT_UNAVAILABLE" || err.status === 422)) {
        // Return to slot selection with the invitee's input intact.
        navigate(`/book/${slug}/slots?conflict=1`, {
          state: { conflict: true, startAt, invitee: { name, email, note } },
        });
        return;
      }
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors as { name?: string; email?: string });
        setError(err.userMessage);
      } else {
        setError("Could not complete the booking. Try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  const displayTz = ev?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone;

  return (
    <Shell title="Your details" subtitle="Almost done — confirm your appointment">
      <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
        {error && <Alert variant="error">{error}</Alert>}
        {startAt && (
          <div className="rounded-md border border-border bg-bg p-3">
            <p className="text-small font-medium text-text">
              {new Date(startAt).toLocaleString(undefined, { timeZone: displayTz, dateStyle: "full", timeStyle: "short" })}
            </p>
            <p className="text-caption text-text-muted">
              {ev?.durationMinutes ?? 30} minutes • {displayTz}
            </p>
          </div>
        )}
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} />
        <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} />
        <Input label="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
        <p className="text-caption text-text-muted">
          By confirming, you agree to the host's cancellation policy shown on the event page.
        </p>
        <Button type="submit" loading={submitting}>
          {submitting ? "Confirming your appointment…" : "Confirm booking"}
        </Button>
      </form>
    </Shell>
  );
}
