import { isErrorEnvelope } from "../types/api";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "/api/v1").replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string;

  constructor(options: {
    message: string;
    status: number;
    code: string;
    details: unknown;
    requestId: string;
  }) {
    super(options.message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.details = options.details;
    this.requestId = options.requestId;
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");

  let response: Response;
  try {
    response = await fetch(url, { ...init, headers });
  } catch {
    throw new ApiError({
      message: "Unable to reach the API.",
      status: 0,
      code: "NETWORK_ERROR",
      details: null,
      requestId: "",
    });
  }

  const requestId = response.headers.get("x-request-id") ?? "";

  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }

    if (isErrorEnvelope(body)) {
      throw new ApiError({
        message: body.message,
        status: response.status,
        code: body.code,
        details: body.details,
        requestId: body.request_id || requestId,
      });
    }

    throw new ApiError({
      message: `Request failed with status ${response.status}.`,
      status: response.status,
      code: "HTTP_ERROR",
      details: null,
      requestId,
    });
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
