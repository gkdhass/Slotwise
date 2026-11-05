export * from "./slots.js";
export const SLOTWISE_VERSION = "0.0.0";

export const errorCodes = {
  SLOT_UNAVAILABLE: "SLOT_UNAVAILABLE",
  VALIDATION_ERROR: "VALIDATION_ERROR",
  UNAUTHORIZED: "UNAUTHORIZED",
  FORBIDDEN: "FORBIDDEN",
  NOT_FOUND: "NOT_FOUND",
  CONFLICT: "CONFLICT",
  RATE_LIMITED: "RATE_LIMITED",
  INTERNAL: "INTERNAL",
} as const;

export type ErrorCode = (typeof errorCodes)[keyof typeof errorCodes];