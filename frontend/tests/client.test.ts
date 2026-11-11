import { describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "../src/api/client";

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

describe("apiFetch", () => {
  it("returns typed JSON on success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ status: "ok" })));

    await expect(apiFetch<{ status: string }>("/healthz")).resolves.toEqual({ status: "ok" });
  });

  it("maps a standard error envelope to ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            code: "VALIDATION_ERROR",
            message: "The request failed validation.",
            details: { errors: [] },
            request_id: "req-123",
          },
          422,
          { "x-request-id": "req-123" },
        ),
      ),
    );

    try {
      await apiFetch("/events", { method: "POST" });
      throw new Error("expected apiFetch to reject");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      const apiError = error as ApiError;
      expect(apiError.status).toBe(422);
      expect(apiError.code).toBe("VALIDATION_ERROR");
      expect(apiError.requestId).toBe("req-123");
      expect(apiError.details).toEqual({ errors: [] });
    }
  });

  it("falls back to HTTP_ERROR for a non-envelope response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("<html>bad gateway</html>", { status: 502 })),
    );

    await expect(apiFetch("/healthz")).rejects.toMatchObject({
      name: "ApiError",
      status: 502,
      code: "HTTP_ERROR",
    });
  });

  it("returns NETWORK_ERROR when fetch rejects", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(apiFetch("/healthz")).rejects.toMatchObject({
      name: "ApiError",
      status: 0,
      code: "NETWORK_ERROR",
    });
  });
});
