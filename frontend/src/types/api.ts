export interface ErrorEnvelope {
  code: string;
  message: string;
  details: unknown;
  request_id: string;
}

export type CheckStatus = "ok" | "error";

export interface DependencyCheck {
  status: CheckStatus;
  latency_ms: number;
  detail: string | null;
}

export interface ReadinessResponse {
  status: "ok" | "degraded";
  version: string;
  environment: string;
  checks: Record<string, DependencyCheck>;
}

export interface LivenessResponse {
  status: "ok";
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (!isRecord(value)) return false;
  return (
    typeof value.code === "string" &&
    typeof value.message === "string" &&
    typeof value.request_id === "string" &&
    "details" in value
  );
}

function isDependencyCheck(value: unknown): value is DependencyCheck {
  if (!isRecord(value)) return false;
  return (
    (value.status === "ok" || value.status === "error") &&
    typeof value.latency_ms === "number" &&
    (typeof value.detail === "string" || value.detail === null)
  );
}

export function isReadinessResponse(value: unknown): value is ReadinessResponse {
  if (!isRecord(value)) return false;
  if (value.status !== "ok" && value.status !== "degraded") return false;
  if (typeof value.version !== "string" || typeof value.environment !== "string") return false;
  if (!isRecord(value.checks)) return false;
  return Object.values(value.checks).every(isDependencyCheck);
}
