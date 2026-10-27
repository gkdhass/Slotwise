import { Shell } from "../components/Shell";
import { Button } from "../components/Button";
import { StatusBadge } from "../components/StatusBadge";

export default function S05PreviewPublish() {
  return (
    <Shell title="Preview and publish" subtitle="Review your booking page">
      <div className="flex flex-col gap-4">
        <div className="rounded-md border border-border p-4">
          <p className="text-body font-medium text-text">Intro tutoring</p>
          <p className="text-small text-text-muted">30 minutes • Online • Asia/Kolkata</p>
          <div className="mt-2">
            <StatusBadge status="draft" />
          </div>
        </div>
        <div className="flex gap-2">
          <Button>Publish booking page</Button>
          <Button variant="secondary">Save draft</Button>
        </div>
      </div>
    </Shell>
  );
}