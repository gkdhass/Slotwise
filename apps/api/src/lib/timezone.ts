/**
 * `isIanaZone` constructs an `Intl.DateTimeFormat`, which costs ~0.5 ms — 2 % of
 * the slots endpoint's CPU when it runs on every request. The set of valid zones
 * is small and fixed, so validated zones are remembered.
 *
 * Shared by the public, management and owner routes: an event must not be
 * created with a zone the slots generator will later throw on, and a visitor's
 * display zone must be validated before it reaches `Intl`.
 */
const VALID_ZONES = new Set<string>();
const CACHE_LIMIT = 500;

export function isIanaZone(tz: string): boolean {
  if (VALID_ZONES.has(tz)) return true;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: tz });
    if (VALID_ZONES.size < CACHE_LIMIT) VALID_ZONES.add(tz);
    return true;
  } catch {
    return false;
  }
}
