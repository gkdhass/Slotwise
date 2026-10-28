import { useEffect, useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";
import { ApiError, getEventTypeBySlug, getSlots } from "../lib/api";
import type { Slot } from "../lib/types";
import { MAX_SLOT_RANGE_DAYS } from "@slotwise/shared";

type InviteeDraft = { name: string; email: string; note: string };

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

/** Local calendar date (YYYY-MM-DD) of an instant in a given IANA zone. */
function dateInZone(iso: string, tz: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(
    new Date(iso),
  );
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

export default function S07SlotSelector() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state ?? {}) as {
    conflict?: boolean;
    invitee?: InviteeDraft;
    startAt?: string;
  };
  const params = new URLSearchParams(location.search);

  const [date, setDate] = useState(todayIso);
  const [dateInitialised, setDateInitialised] = useState(false);
  const [tzResolved, setTzResolved] = useState(false);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [tz, setTz] = useState("Asia/Kolkata");
  const [error, setError] = useState<string | null>(null);
  const conflict = state.conflict || params.get("conflict") === "1";

  useEffect(() => {
    if (!slug) return;
    (async () => {
      try {
        const e = await getEventTypeBySlug(slug);
        if (e) setTz(e.timezone);
      } catch (err) {
        setError(err instanceof ApiError ? err.userMessage : "Could not load this event.");
      } finally {
        setTzResolved(true);
      }
    })();
  }, [slug]);

  // Coming back from a conflict (or arriving from a deep link) we know the
  // attempted instant. Slots are filtered in the event's time zone, so the date
  // input must be derived in that same zone — hence we wait for the event zone.
  useEffect(() => {
    if (dateInitialised) return;
    if (state.startAt) {
      if (!tzResolved) return;
      setDate(dateInZone(state.startAt, tz));
    }
    setDateInitialised(true);
  }, [state.startAt, tz, tzResolved, dateInitialised]);

  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    // Query a 3-day window so any zone offset is covered, then filter to the
    // chosen date in the event's time zone. The window is clamped to the API's
    // documented maximum (MAX_SLOT_RANGE_DAYS) so client and server cannot drift.
    const base = new Date(`${date}T00:00:00Z`).getTime();
    const from = new Date(base - 86_400_000).toISOString();
    const to = new Date(Math.min(base + 2 * 86_400_000, base + MAX_SLOT_RANGE_DAYS * 86_400_000)).toISOString();
    getSlots(slug, from, to, tz)
      .then((all) => {
        if (cancelled) return;
        setSlots(all.filter((s) => dateInZone(s.startAt, tz) === date));
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.userMessage : "Could not load times.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [slug, date, tz]);

  function handleContinue() {
    if (!selected || !slug) return;
    navigate(`/book/${slug}/details?start=${encodeURIComponent(selected)}`, {
      state: { invitee: state.invitee },
    });
  }

  return (
    <Shell title="Choose a time" subtitle={`Slots shown in ${tz}`}>
      <div className="flex flex-col gap-4">
        {conflict && (
          <Alert variant="error" title="That time was just taken.">
            Pick another time. Your name, email and note were kept.
          </Alert>
        )}
        {error && <Alert variant="error">{error}</Alert>}
        <InputDate label="Date" value={date} onChange={(v) => { setDate(v); setSelected(null); }} />
        {loading && <p className="text-text-muted">Loading slots…</p>}
        {!loading && slots.length === 0 && !error && (
          <p className="text-small text-text-muted">No times are open for these dates. Try another day.</p>
        )}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {slots.map((s) => (
            <button
              key={s.startAt}
              type="button"
              onClick={() => setSelected(s.startAt)}
              aria-pressed={selected === s.startAt}
              className={`rounded-md border px-3 py-2 text-small ${
                selected === s.startAt
                  ? "border-accent bg-accent text-on-accent"
                  : "border-border bg-surface text-text hover:border-accent"
              }`}
            >
              {s.label}
              <span className="block text-caption opacity-80">{tz}</span>
            </button>
          ))}
        </div>
        <Button onClick={handleContinue} disabled={!selected}>
          Continue
        </Button>
      </div>
    </Shell>
  );
}

function InputDate({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const id = "slot-date";
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-small font-medium text-text">
        {label}
      </label>
      <input
        id={id}
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-border-input px-3 py-2 text-body text-text"
      />
    </div>
  );
}
