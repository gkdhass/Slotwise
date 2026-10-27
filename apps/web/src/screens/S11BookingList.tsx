import { Shell } from "../components/Shell";
import { StatusBadge } from "../components/StatusBadge";

const mock = [
  { id: "1", invitee: "Alex Example", when: "Mon 2 Nov 2026 10:00 AM", status: "confirmed" as const },
  { id: "2", invitee: "Sam Student", when: "Tue 3 Nov 2026 2:30 PM", status: "canceled" as const },
];

export default function S11BookingList() {
  return (
    <Shell title="Bookings" subtitle="Your appointments">
      <ul className="flex flex-col gap-3">
        {mock.map((b) => (
          <li key={b.id} className="flex items-center justify-between rounded-md border border-border p-3">
            <div>
              <p className="text-body font-medium text-text">{b.invitee}</p>
              <p className="text-small text-text-muted">{b.when}</p>
            </div>
            <StatusBadge status={b.status} />
          </li>
        ))}
      </ul>
    </Shell>
  );
}