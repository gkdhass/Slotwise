import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Input } from "../components/Input";
import { Button } from "../components/Button";
import { getEventType, updateEventType, createEventType } from "../lib/mockApi";
import type { EventType } from "../lib/types";

export default function S03EventEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const isNew = !id || id === "new";
  const [ev, setEv] = useState<EventType | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [duration, setDuration] = useState("30");
  const [locationType, setLocationType] = useState("online");
  const [locationDetails, setLocationDetails] = useState("");
  const [timezone, setTimezone] = useState("Asia/Kolkata");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      if (isNew) {
        const created = await createEventType({ title: "New session" });
        setEv(created);
        setTitle(created.title);
        setTimezone(created.timezone);
        navigate(`/app/events/${created.id}/edit`, { replace: true });
      } else if (id) {
        const e = await getEventType(id);
        if (e) {
          setEv(e);
          setTitle(e.title);
          setDescription(e.description);
          setDuration(String(e.durationMinutes));
          setLocationType(e.locationType);
          setLocationDetails(e.locationDetails);
          setTimezone(e.timezone);
        }
      }
    })();
  }, [id, isNew, navigate]);

  async function handleSave() {
    if (!ev) return;
    setSaving(true);
    await updateEventType(ev.id, {
      title,
      description,
      durationMinutes: Number(duration) || 30,
      locationType: locationType as EventType["locationType"],
      locationDetails,
      timezone,
    });
    setSaving(false);
  }

  return (
    <Shell title="Event editor" subtitle="What should this session be called?">
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          handleSave();
        }}
      >
        <Input label="What should this session be called?" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Input label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
        <Input
          label="How long should the session last? (minutes)"
          type="number"
          value={duration}
          onChange={(e) => setDuration(e.target.value)}
        />
        <Input
          label="Location type (custom/phone/online)"
          value={locationType}
          onChange={(e) => setLocationType(e.target.value)}
        />
        <Input
          label="Location details"
          value={locationDetails}
          onChange={(e) => setLocationDetails(e.target.value)}
        />
        <Input label="Time zone (IANA)" value={timezone} onChange={(e) => setTimezone(e.target.value)} />
        <div className="flex gap-2">
          <Button type="submit" loading={saving}>
            Save
          </Button>
          {ev && (
            <Button variant="secondary" onClick={() => navigate(`/app/events/${ev.id}/availability`)}>
              Availability
            </Button>
          )}
          {ev && (
            <Button variant="ghost" onClick={() => navigate(`/app/events/${ev.id}/preview`)}>
              Preview
            </Button>
          )}
        </div>
      </form>
    </Shell>
  );
}