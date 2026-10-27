import { Shell } from "../components/Shell";
import { Button } from "../components/Button";
import { Dialog } from "../components/Dialog";
import { useState } from "react";

export default function S10Management() {
  const [open, setOpen] = useState(false);
  return (
    <Shell title="Manage booking" subtitle="Cancel or reschedule">
      <div className="flex flex-col gap-4">
        <p className="text-body text-text">Monday, 2 Nov 2026, 10:00 AM Asia/Kolkata</p>
        <div className="flex gap-2">
          <Button variant="danger" onClick={() => setOpen(true)}>
            Cancel
          </Button>
          <Button variant="secondary">Reschedule</Button>
        </div>
        <Dialog open={open} onClose={() => setOpen(false)} title="Cancel booking?">
          <p className="text-body text-text-muted">This will release the time slot. This action cannot be undone.</p>
        </Dialog>
      </div>
    </Shell>
  );
}