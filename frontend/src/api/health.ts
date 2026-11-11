import { ApiError, apiFetch } from "./client";
import { isReadinessResponse, type LivenessResponse, type ReadinessResponse } from "../types/api";

export const healthQueryKeys = {
  live: ["health", "live"] as const,
  ready: ["health", "ready"] as const,
};

export function fetchLiveness(): Promise<LivenessResponse> {
  return apiFetch<LivenessResponse>("/healthz");
}

export function fetchReadiness(): Promise<ReadinessResponse> {
  return apiFetch<ReadinessResponse>("/readyz");
}

/**
 * A 503 readiness response is still a health report. Recover the per-dependency
 * details from the standard error envelope so the UI can show a degraded state.
 */
export function readinessFromError(error: unknown): ReadinessResponse | null {
  if (error instanceof ApiError && isReadinessResponse(error.details)) {
    return error.details;
  }
  return null;
}
