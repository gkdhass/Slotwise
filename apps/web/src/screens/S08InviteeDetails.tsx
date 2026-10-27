import { useState } from "react";
import { useParams, useSearchParams, useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Input } from "../components/Input";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";
import { createBooking } from "../lib/mockApi";

export default function S08InviteeDetails() {
  const { slug } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const startAt = params.get("start") ?? "";
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [errors, setErrors] = useState<{ name?: string; email?: string }>({});
  const [submitting, setSubmitting] = useState(false);
  const [conflict, setConflict] = useState(false);

  function validate() {
    const e: typeof errors = {};
    if (!name.trim()) e.name = "Name is required";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) e.email = "Enter a valid email";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function handleSubmit(ev: React.FormEvent) {
    ev.preventDefault();
    if (!validate()) return;
    setSubmitting(true);
    setConflict(false);
    try {
      const booking = await createBooking(slug!, {
        startAt,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        invitee: { name, email, note },
        idempotencyKey: `key-${slug}-${startAt}-${email}`,
      });
      navigate(`/booking/confirmed/${booking.reference}`);
    } catch (err) {
      if (String(err).includes("SLOT_UNAVAILABLE")) setConflict(true);
      else setErrors({ email: "Could not complete booking. Try again." });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Shell title="Your details" subtitle="Almost done — confirm your appointment">
      <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
        {conflict && (
          <Alert variant="error" title="That time is no longer available.">
            Choose another slot. Your details have been preserved.
          </Alert>
        )}
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} />
        <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} />
        <Input label="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
        <Button type="submit" loading={submitting}>
          {submitting ? "Confirming your appointment…" : "Confirm booking"}
        </Button>
      </form>
    </Shell>
  );
}