import { Shell } from "../components/Shell";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";

export default function S09Confirmation() {
  return (
    <Shell title="Your appointment is confirmed" subtitle="Booking reference: demo-001">
      <div className="flex flex-col gap-4">
        <Alert variant="success">Your appointment is confirmed.</Alert>
        <p className="text-body text-text">Monday, 2 Nov 2026, 10:00 AM Asia/Kolkata (30 minutes)</p>
        <div className="flex gap-2">
          <Button variant="secondary">Cancel</Button>
          <Button variant="secondary">Reschedule</Button>
        </div>
      </div>
    </Shell>
  );
}