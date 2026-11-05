import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Input } from "../components/Input";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";
import { ApiError, getEventType, updateEventType, createEventType } from "../lib/api";
import type { EventType } from "../lib/types";

export default function S03EventEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const isNew = !id || id === "new";
  const [ev, setEv] = useState<EventType | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [duration, setDuration] = useState("30");
  const [locationType, setLocationType] = useState<EventType["locationType"]>("online");
  const [locationDetails, setLocationDetails] = useState("");
  const [timezone, setTimezone] = useState("Asia/Kolkata");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        if (isNew) {
          const created = await createEventType({ title: "New session", timezone: "Asia/Kolkata" });
          navigate(`/app/events/${created.id}/edit`, { replace: true });
        } else if (id) {
          const e = await getEventType(id);
          if (!e) {
            setError("We could not find that session.");
            return;
          }
          setEv(e);
          setTitle(e.title);
          setDescription(e.description);
          setDuration(String(e.durationMinutes));
          setLocationType(e.locationType);
          setLocationDetails(e.locationDetails);
          setTimezone(e.timezone);
        }
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          navigate("/login");
          return;
        }
        setError(err instanceof ApiError ? err.userMessage : "Could not load this session.");
      }
    })();
  }, [id, isNew, navigate]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!ev) return;
    setSaving(true);
    setError(null);
    setFieldErrors({});
    setSaved(false);
    try {
      const minutes = Number(duration);
      if (!Number.isFinite(minutes) || minutes < 5 || minutes > 480) {
        setFieldErrors({ durationMinutes: "Duration must be between 5 and 480 minutes." });
        return;
      }
      const updated = await updateEventType(ev.id, {
        title,
        description,
        durationMinutes: minutes,
        locationType,
        locationDetails,
        timezone,
      });
      setEv(updated);
      setSaved(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors);
        setError(err.userMessage);
      } else {
        setError("Could not save this session.");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <Shell title="Event editor" subtitle="What should this session be called?">
      <form className="flex flex-col gap-4" onSubmit={handleSave} noValidate>
        {error && <Alert variant="error">{error}</Alert>}
        {saved && <Alert variant="success">Session saved.</Alert>}
        <Input
          label="What should this session be called?"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          error={fieldErrors.title}
        />
        <Input label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
        <Input
          label="How long should the session last? (minutes)"
          type="number"
          value={duration}
          onChange={(e) => setDuration(e.target.value)}
          error={fieldErrors.durationMinutes}
        />
        <div className="flex flex-col gap-1">
          <label htmlFor="location-type" className="text-small font-medium text-text">
            Location type
          </label>
          <select
            id="location-type"
            value={locationType}
            onChange={(e) => setLocationType(e.target.value as EventType["locationType"])}
            className="rounded-md border border-border-input px-3 py-2 text-body text-text"
          >
            <option value="online">Online</option>
            <option value="phone">Phone</option>
            <option value="custom">Custom</option>
          </select>
        </div>
        <Input label="Location details" value={locationDetails} onChange={(e) => setLocationDetails(e.target.value)} />
        <Input
          label="Time zone (IANA)"
          value={timezone}
          onChange={(e) => setTimezone(e.target.value)}
          error={fieldErrors.timezone}
        />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" loading={saving}>
            Save
          </Button>
          {ev && (
            <Button type="button" variant="secondary" onClick={() => navigate(`/app/events/${ev.id}/availability`)}>
              Availability
            </Button>
          )}
          {ev && (
            <Button type="button" variant="ghost" onClick={() => navigate(`/app/events/${ev.id}/preview`)}>
              Preview
            </Button>
          )}
        </div>
      </form>
    </Shell>
  );
}
