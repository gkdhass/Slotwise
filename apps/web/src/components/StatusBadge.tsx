type Status = "draft" | "published" | "confirmed" | "canceled" | "completed" | "no_show";

const styles: Record<Status, string> = {
  draft: "bg-bg text-text-muted",
  published: "bg-green-50 text-success",
  confirmed: "bg-green-50 text-success",
  canceled: "bg-red-50 text-danger",
  completed: "bg-blue-50 text-text",
  no_show: "bg-amber-50 text-warning",
};

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span className={`inline-flex items-center rounded-pill px-2 py-0.5 text-caption font-medium ${styles[status]}`}>
      {status.replace("_", " ")}
    </span>
  );
}