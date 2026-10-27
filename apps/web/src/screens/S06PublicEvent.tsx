import { Shell } from "../components/Shell";
import { Button } from "../components/Button";

export default function S06PublicEvent() {
  return (
    <Shell title="One-to-one tutoring session" subtitle="30 minutes • Online • Time zone shown">
      <div className="flex flex-col gap-4">
        <p className="text-body text-text-muted">Hosted by your tutor. Pick a time that works for you.</p>
        <Button>Choose a time</Button>
      </div>
    </Shell>
  );
}