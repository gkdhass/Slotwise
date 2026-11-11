import { ApiError } from "../../api/client";
import { readinessFromError } from "../../api/health";
import { useHealthQueries } from "../../hooks/useHealth";
import type { CheckStatus, ReadinessResponse } from "../../types/api";
import { StatusBadge } from "../../components/StatusBadge";

const DEPENDENCIES = ["postgres", "redis", "opensearch", "minio", "mlflow"] as const;

type OverallTone = "operational" | "degraded" | "offline" | "checking";

const OVERALL_COPY: Record<OverallTone, { title: string; detail: string; classes: string }> = {
  operational: {
    title: "Operational",
    detail: "All checked dependencies are responding.",
    classes: "border-teal/50 bg-pale-cyan text-deep-blue",
  },
  degraded: {
    title: "Degraded",
    detail: "One or more dependencies are unavailable. Investigate before acting.",
    classes: "border-warning/60 bg-warning/15 text-deep-blue",
  },
  offline: {
    title: "Offline",
    detail: "The API cannot be reached. Check the reverse proxy and API logs.",
    classes: "border-critical/50 bg-critical/10 text-critical",
  },
  checking: {
    title: "Checking",
    detail: "Contacting the API and its dependencies…",
    classes: "border-navy/15 bg-white text-muted",
  },
};

function formatLatency(value: number): string {
  return `${value.toFixed(1)} ms`;
}

function DependencyRow({
  name,
  status,
  latency,
  detail,
}: {
  name: string;
  status: CheckStatus | "pending";
  latency: number | null;
  detail: string | null;
}) {
  return (
    <tr className="border-t border-navy/10">
      <th scope="row" className="px-4 py-3 text-left font-medium capitalize text-ink">
        {name}
      </th>
      <td className="px-4 py-3">
        <StatusBadge status={status} />
      </td>
      <td className="px-4 py-3 text-sm tabular-nums text-muted">
        {latency === null ? "—" : formatLatency(latency)}
      </td>
      <td className="px-4 py-3 text-sm text-muted">{detail ?? "—"}</td>
    </tr>
  );
}

function ReadinessTable({ report }: { report: ReadinessResponse | null }) {
  return (
    <div className="overflow-x-auto rounded-card border border-navy/10 bg-white shadow-panel">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">Dependency readiness</caption>
        <thead className="bg-pale-cyan/60 text-left text-xs uppercase tracking-wide text-deep-blue">
          <tr>
            <th scope="col" className="px-4 py-3">
              Dependency
            </th>
            <th scope="col" className="px-4 py-3">
              Status
            </th>
            <th scope="col" className="px-4 py-3">
              Latency
            </th>
            <th scope="col" className="px-4 py-3">
              Detail
            </th>
          </tr>
        </thead>
        <tbody>
          {DEPENDENCIES.map((name) => {
            const check = report?.checks[name] ?? null;
            return (
              <DependencyRow
                key={name}
                name={name}
                status={check?.status ?? "pending"}
                latency={check?.latency_ms ?? null}
                detail={check?.detail ?? null}
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function describeError(error: unknown): string | null {
  if (!error) return null;
  if (error instanceof ApiError) {
    return error.requestId ? `${error.message} (request ${error.requestId})` : error.message;
  }
  return "The API request failed.";
}

export function HealthPage() {
  const { liveness, readiness } = useHealthQueries();
  const report = readiness.data ?? readinessFromError(readiness.error);

  let overall: OverallTone = "checking";
  if (liveness.isError) {
    overall = "offline";
  } else if (report) {
    overall = report.status === "ok" ? "operational" : "degraded";
  } else if (readiness.isError) {
    overall = "degraded";
  } else if (liveness.isSuccess && readiness.isSuccess) {
    overall = "operational";
  }

  const copy = OVERALL_COPY[overall];
  const errorMessage = describeError(readiness.error);
  const liveErrorMessage = describeError(liveness.error);
  const lastUpdated = readiness.dataUpdatedAt
    ? new Date(readiness.dataUpdatedAt).toLocaleTimeString()
    : null;

  const refresh = () => {
    void liveness.refetch();
    void readiness.refetch();
  };

  return (
    <section className="space-y-6" aria-labelledby="health-heading">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal">Operations</p>
          <h1 id="health-heading" className="mt-1 text-2xl font-bold text-navy">
            System health
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Live status for the API and every Phase 1 dependency. Values come from{" "}
            <code className="rounded bg-navy/5 px-1 py-0.5 text-xs">/api/v1/healthz</code> and{" "}
            <code className="rounded bg-navy/5 px-1 py-0.5 text-xs">/api/v1/readyz</code>.
          </p>
        </div>
        <button
          type="button"
          onClick={refresh}
          className="rounded-control bg-teal px-4 py-2 text-sm font-semibold text-white transition hover:bg-teal/90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy"
        >
          Refresh status
        </button>
      </div>

      <div
        role="status"
        aria-live="polite"
        className={`rounded-card border p-5 shadow-panel ${copy.classes}`}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-bold">{copy.title}</h2>
          {lastUpdated ? (
            <span className="text-xs text-muted">Last checked {lastUpdated}</span>
          ) : null}
        </div>
        <p className="mt-1 text-sm">{copy.detail}</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-card border border-navy/10 bg-white p-5 shadow-panel">
          <p className="text-xs uppercase tracking-wide text-muted">Liveness</p>
          <div className="mt-2">
            <StatusBadge
              status={liveness.isSuccess ? "ok" : liveness.isError ? "error" : "pending"}
            />
          </div>
          <p className="mt-3 text-sm text-muted">
            {liveness.isSuccess
              ? "API process is serving requests."
              : (liveErrorMessage ?? "Waiting for the API…")}
          </p>
        </div>

        <div className="rounded-card border border-navy/10 bg-white p-5 shadow-panel">
          <p className="text-xs uppercase tracking-wide text-muted">Readiness</p>
          <div className="mt-2">
            <StatusBadge
              status={
                report
                  ? report.status === "ok"
                    ? "ok"
                    : "error"
                  : readiness.isError
                    ? "error"
                    : "pending"
              }
            />
          </div>
          <p className="mt-3 text-sm text-muted">
            {report
              ? `${Object.values(report.checks).filter((check) => check.status === "ok").length}/${Object.keys(report.checks).length} dependencies healthy.`
              : (errorMessage ?? "Waiting for dependency checks…")}
          </p>
        </div>

        <div className="rounded-card border border-navy/10 bg-white p-5 shadow-panel">
          <p className="text-xs uppercase tracking-wide text-muted">Build</p>
          <p className="mt-2 text-lg font-bold text-navy">{report?.version ?? "—"}</p>
          <p className="mt-1 text-sm text-muted">
            Environment: <span className="font-medium">{report?.environment ?? "unknown"}</span>
          </p>
          <p className="mt-1 text-xs text-muted">Module B is disabled unless explicitly enabled.</p>
        </div>
      </div>

      <ReadinessTable report={report} />

      {errorMessage ? (
        <p
          role="alert"
          className="rounded-card border border-critical/30 bg-critical/5 px-4 py-3 text-sm text-critical"
        >
          {errorMessage}
        </p>
      ) : null}
    </section>
  );
}
