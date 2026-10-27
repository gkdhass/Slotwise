import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Input } from "../components/Input";
import { Button } from "../components/Button";
import { getEventType, getAvailability, setAvailability } from "../lib/mockApi";
import type { AvailabilityRule } from "../lib/types";

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

type Row = { start: string; end: string; enabled: boolean };

export default function S04Availability() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [tz, setTz] = useState("Asia/Kolkata");
  const [rows, setRows] = useState<Row[]>(
    DAYS.map(() => ({ start: "10:00", end: "17:00", enabled: false })),
  );
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!id) return;
    (async () => {
      const ev = await getEventType(id);
      if (ev) setTz(ev.timezone);
      const rules = await getAvailability(id);
      const next = DAYS.map(() => ({ start: "10:00", end: "17:00", enabled: false }));
      for (const r of rules) {
        next[r.weekday] = { start: r.startLocal, end: r.endLocal, enabled: true };
      }
      setRows(next);
    })();
  }, [id]);

  async function handleSave() {
    if (!id) return;
    setSaving(true);
    const rules: AvailabilityRule[] = rows
      .map((r, i) =>
        r.enabled
          ? {
              id: `ar-${id}-${i}`,
              eventTypeId: id,
              weekday: i,
              startLocal: r.start,
              endLocal: r.end,
              timezone: tz,
            }
          : null,
      )
      .filter(Boolean) as AvailabilityRule[];
    await setAvailability(id, rules);
    setSaving(false);
  }

  return (
    <Shell title="Availability" subtitle="Choose the hours you can meet">
      <div className="flex flex-col gap-3">
        {DAYS.map((d, i) => (
          <div key={d} className="flex items-center gap-3 rounded-md border border-border p-3">
            <label className="flex items-center gap-2 text-small font-medium text-text">
              <input
                type="checkbox"
                checked={rows[i].enabled}
                onChange={(e) => {
                  const next = [...rows];
                  next[i] = { ...next[i], enabled: e.target.checked };
                  setRows(next);
                }}
              />
              {d}
            </label>
            <Input
              label={`${d} start`}
              type="time"
              value={rows[i].start}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...next[i], start: e.target.value };
                setRows(next);
              }}
            />
            <Input
              label={`${d} end`}
              type="time"
              value={rows[i].end}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...next[i], end: e.target.value };
                setRows(next);
              }}
            />
          </div>
        ))}
        <div className="flex gap-2">
          <Button onClick={handleSave} loading={saving}>
            Save availability
          </Button>
          {id && (
            <Button variant="secondary" onClick={() => navigate(`/app/events/${id}/preview`)}>
              Preview
            </Button>
          )}
        </div>
      </div>
    </Shell>
  );
}