/**
 * Single source of "now" for scheduling logic.
 *
 * Why this exists: the availability grid is computed relative to the current
 * instant (past slots are hidden), so a test that asserts on a specific
 * calendar date silently starts failing once real time moves past it. Tests
 * freeze the clock instead and the assertions stay valid forever.
 *
 * Scope: everything in the scheduling domain — slot generation, booking and
 * reschedule validation, management-token expiry, and outbox scheduling
 * timestamps. Infrastructure that must follow real wall time (rate limiting,
 * session/verification tokens, worker backoff) deliberately keeps `Date.now()`.
 *
 * Safety: the override is refused outright when NODE_ENV=production, so a
 * frozen clock can never reach a real deployment.
 */

let frozen: Date | null = null;

/** The current instant. Always returns a fresh Date so callers cannot mutate it. */
export function now(): Date {
  return frozen ? new Date(frozen.getTime()) : new Date();
}

/** Freezes the clock for a test. Rejects production and invalid instants. */
export function setNowForTesting(at: Date | string | number): void {
  if (process.env.NODE_ENV === "production") {
    throw new Error("Clock override is not available when NODE_ENV=production");
  }
  const at_ = at instanceof Date ? new Date(at.getTime()) : new Date(at);
  if (Number.isNaN(at_.getTime())) {
    throw new Error(`Invalid clock instant: ${String(at)}`);
  }
  frozen = at_;
}

/** Returns the clock to real time. Safe to call when no override is set. */
export function resetNowForTesting(): void {
  frozen = null;
}

/** Whether an override is currently active (for assertions and debugging). */
export function isFrozenForTesting(): boolean {
  return frozen !== null;
}
