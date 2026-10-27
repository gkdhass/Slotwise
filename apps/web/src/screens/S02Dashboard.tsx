import { Shell } from "../components/Shell";
import { Button } from "../components/Button";
import { StatusBadge } from "../components/StatusBadge";

const mockEvents = [
  { id: "1", title: "Intro tutoring", duration: 30, status: "published" as const },
  { id: "2", title: "Follow-up session", duration: 45, status: "draft" as const },
];

export default function S02Dashboard() {
  return (
    <Shell title="Dashboard" subtitle="Manage your event types and appointments">
      <div className="flex items-center justify-between">
        <p className="text-body text-text-muted">Your event types</p>
        <Button>Create event</Button>
      </div>
      <ul className="mt-4 flex flex-col gap-3">
        {mockEvents.map((e) => (
          <li key={e.id} className="flex items-center justify-between rounded-md border border-border p-3">
            <div>
              <p className="text-body font-medium text-text">{e.title}</p>
              <p className="text-small text-text-muted">{e.duration} minutes</p>
            </div>
            <StatusBadge status={e.status} />
          </li>
        ))}
      </ul>
    </Shell>
  );
}