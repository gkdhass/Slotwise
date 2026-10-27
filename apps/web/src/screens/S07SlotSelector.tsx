import { Shell } from "../components/Shell";
import { Button } from "../components/Button";

const slots = ["Mon 10:00 AM", "Mon 11:00 AM", "Tue 2:30 PM"];

export default function S07SlotSelector() {
  return (
    <Shell title="Choose a time" subtitle="Slots shown in Asia/Kolkata">
      <div className="flex flex-col gap-3">
        {slots.map((s) => (
          <button
            key={s}
            type="button"
            className="rounded-md border border-border bg-surface px-4 py-3 text-left text-body text-text hover:border-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            {s}
          </button>
        ))}
        <p className="text-small text-text-muted">No times are open for these dates. Try another day.</p>
        <Button>Continue</Button>
      </div>
    </Shell>
  );
}