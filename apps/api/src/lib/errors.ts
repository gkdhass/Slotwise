export class AppError extends Error {
  constructor(
    public code: string,
    public status: number,
    message: string,
    public fieldErrors: Record<string, string> = {},
  ) {
    super(message);
  }
}

export const Errors = {
  validation: (msg = "Check the highlighted fields and try again.", fieldErrors: Record<string, string> = {}) =>
    new AppError("VALIDATION_ERROR", 400, msg, fieldErrors),
  unauthorized: () => new AppError("UNAUTHORIZED", 401, "Authentication required."),
  forbidden: () => new AppError("FORBIDDEN", 403, "You are not allowed to do that."),
  notFound: () => new AppError("NOT_FOUND", 404, "Resource not found."),
  conflict: (code = "CONFLICT", msg = "Conflict.") => new AppError(code, 409, msg),
  slotUnavailable: () =>
    new AppError("SLOT_UNAVAILABLE", 409, "That time is no longer available. Choose another slot."),
  rateLimited: () => new AppError("RATE_LIMITED", 429, "Too many requests. Try again later."),
  internal: () => new AppError("INTERNAL", 500, "Unexpected server error."),
};