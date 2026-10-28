import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Button } from "../components/Button";
import { getEventTypeBySlug, getSlots } from "../lib/mockApi";
import type { Slot } from "../lib/types";

export default function S07SlotSelector() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [slots, setSlots] = useState<Slot[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [tz, setTz] = useState("Asia/Kolkata");

  useEffect(() => {
    if (!slug) return;
    getEventTypeBySlug(slug).then((e) => e && setTz(e.timezone));
  }, [slug]);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    const from = new Date(date + "T00:00:00Z").toISOString();
    const to = new Date(new Date(date + "T00:00:00Z").getTime() + 86400000).toISOString();
    getSlots(slug, from, to, tz).then((s) => {
      setSlots(s);
      setLoading(false);
    });
  }, [slug, date, tz]);

  function handleContinue() {
    if (!selected || !slug) return;
    navigate(`/book/${slug}/details?start=${encodeURIComponent(selected)}`);
  }

  return (
    <Shell title="Choose a time" subtitle={`Slots shown in ${tz}`}>
      <div className="flex flex-col gap-4">
        <InputDate label="Date" value={date} onChange={setDate} />
        {loading && <p className="text-text-muted">Loading slots…</p>}
        {!loading && slots.length === 0 && (
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