import type { CheckStatus } from "../types/api";

type Tone = "ok" | "error" | "pending";

const TONE_STYLES: Record<Tone, string> = {
  ok: "border-teal/40 bg-pale-cyan text-deep-blue",
  error: "border-critical/40 bg-critical/10 text-critical",
  pending: "border-warning/50 bg-warning/15 text-deep-blue",
};

const LABELS: Record<Tone, string> = {
  ok: "Healthy",
  error: "Error",
  pending: "Checking",
};

export function StatusBadge({ status }: { status: CheckStatus | "pending" }) {
  const tone: Tone = status === "ok" ? "ok" : status === "error" ? "error" : "pending";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${TONE_STYLES[tone]}`}
    >
      <span aria-hidden="true">{tone === "ok" ? "✓" : tone === "error" ? "!" : "…"}</span>
      {LABELS[tone]}
    </span>
  );
}
