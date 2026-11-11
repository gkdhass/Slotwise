import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HealthPage } from "../src/features/health/HealthPage";
import type { ReadinessResponse } from "../src/types/api";

const healthyReadiness: ReadinessResponse = {
  status: "ok",
  version: "0.1.0",
  environment: "test",
  checks: {
    postgres: { status: "ok", latency_ms: 2.1, detail: null },
    redis: { status: "ok", latency_ms: 0.8, detail: null },
    opensearch: { status: "ok", latency_ms: 5.4, detail: null },
    minio: { status: "ok", latency_ms: 3.2, detail: null },
    mlflow: { status: "ok", latency_ms: 4.5, detail: null },
  },
};

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <HealthPage />
    </QueryClientProvider>,
  );
}

function mockApi(readinessResponse: Response) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/healthz")) return Promise.resolve(jsonResponse({ status: "ok" }));
      if (url.endsWith("/readyz")) return Promise.resolve(readinessResponse);
      return Promise.resolve(jsonResponse({ message: "not found" }, 404));
    }),
  );
}

describe("HealthPage", () => {
  it("renders operational status and each dependency", async () => {
    mockApi(jsonResponse(healthyReadiness));
    renderPage();

    expect(await screen.findByText("Operational")).toBeInTheDocument();
    expect(screen.getByText("0.1.0")).toBeInTheDocument();

    const redisRow = screen.getByRole("row", { name: /redis/i });
    expect(within(redisRow).getByText("Healthy")).toBeInTheDocument();
    expect(within(redisRow).getByText("0.8 ms")).toBeInTheDocument();

    expect(screen.getByText(/5\/5 dependencies healthy/)).toBeInTheDocument();
  });

  it("renders degraded status from a 503 readiness envelope", async () => {
    const degraded: ReadinessResponse = {
      ...healthyReadiness,
      status: "degraded",
      checks: {
        ...healthyReadiness.checks,
        redis: { status: "error", latency_ms: 0.4, detail: "connection_error" },
      },
    };
    mockApi(
      jsonResponse(
        {
          code: "DEPENDENCY_UNAVAILABLE",
          message: "One or more dependencies are unavailable.",
          details: degraded,
          request_id: "req-degraded-1",
        },
        503,
        { "x-request-id": "req-degraded-1" },
      ),
    );
    renderPage();

    expect(await screen.findByText("Degraded")).toBeInTheDocument();
    const redisRow = screen.getByRole("row", { name: /redis/i });
    expect(within(redisRow).getByText("Error")).toBeInTheDocument();
    expect(within(redisRow).getByText("connection_error")).toBeInTheDocument();
    expect(screen.getByText(/4\/5 dependencies healthy/)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("req-degraded-1");
  });
});
