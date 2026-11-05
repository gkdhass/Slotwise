import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const API = "http://localhost:4000";
export const SLUG = "intro-tutoring";
export const OWNER = { email: "e2e.owner@slotwise.test", password: "e2e-password-123" };
export const HOST_TZ = "Asia/Kolkata";

/** Signs the owner in through the real S01 screen. */
export async function login(page: Page, email = OWNER.email, password = OWNER.password) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
}

/**
 * Date (YYYY-MM-DD) of a weekday N weeks from now. Defaults to Monday, which
 * is inside the seeded Mon-Fri 09:00-17:00 availability.
 */
export function upcomingWeekday(weeksAhead = 0, weekday = 1): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + 1);
  while (d.getUTCDay() !== weekday) d.setUTCDate(d.getUTCDate() + 1);
  d.setUTCDate(d.getUTCDate() + weeksAhead * 7);
  return d.toISOString().slice(0, 10);
}

/** Calendar date of an instant in a given IANA zone. */
export function dateInZone(iso: string, tz = HOST_TZ): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(iso));
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

export type Slot = { startAt: string; endAt: string; label: string };

/** Free slots on a given calendar date in the requested zone, from the API. */
export async function slotsForDate(
  request: APIRequestContext,
  date: string,
  tz = HOST_TZ,
): Promise<Slot[]> {
  const base = new Date(`${date}T00:00:00Z`).getTime();
  const from = new Date(base - 86_400_000).toISOString();
  const to = new Date(base + 2 * 86_400_000).toISOString();
  const qs = new URLSearchParams({ from, to, tz });
  const res = await request.get(`${API}/api/v1/public/${SLUG}/slots?${qs.toString()}`);
  expect(res.ok(), `slots request failed: ${res.status()} ${await res.text()}`).toBeTruthy();
  const all = (await res.json()) as Slot[];
  return all.filter((s) => dateInZone(s.startAt, tz) === date);
}

export type BookedViaApi = { reference: string; token: string; startAt: string };

/** Books a slot directly against the API (no UI) so other tests have data. */
export async function bookViaApi(
  request: APIRequestContext,
  startAt: string,
  invitee: { name?: string; email?: string; note?: string; timezone?: string } = {},
): Promise<BookedViaApi> {
  const res = await request.post(`${API}/api/v1/public/${SLUG}/bookings`, {
    data: {
      startAt,
      timezone: invitee.timezone ?? HOST_TZ,
      invitee: {
        name: invitee.name ?? "API Invitee",
        email: invitee.email ?? "api.invitee@example.test",
        note: invitee.note ?? "created by the E2E suite",
      },
      idempotencyKey: `e2e-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    },
  });
  expect(res.status(), `booking failed: ${await res.text()}`).toBe(201);
  const body = await res.json();
  expect(body.managementToken).toBeTruthy();
  return { reference: body.reference, token: body.managementToken, startAt: body.booking.startAt };
}

/** Walks the public booking flow from the slot picker to the confirmation page. */
export async function bookThroughUi(
  page: Page,
  opts: {
    date: string;
    index?: number;
    name?: string;
    email?: string;
    note?: string;
  },
) {
  const index = opts.index ?? 0;
  await page.goto(`/book/${SLUG}`);
  await expect(page.getByRole("heading", { name: "Intro tutoring" })).toBeVisible();
  await page.getByRole("button", { name: "Choose a time" }).click();

  await expect(page.getByRole("heading", { name: "Choose a time" })).toBeVisible();
  await page.getByLabel("Date").fill(opts.date);

  const slotButtons = page.locator("button[aria-pressed]");
  await expect(slotButtons.nth(index)).toBeVisible();
  const chosenLabel = await slotButtons.nth(index).innerText();
  await slotButtons.nth(index).click();
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByRole("heading", { name: "Your details" })).toBeVisible();
  await page.getByLabel("Name").fill(opts.name ?? "E2E Invitee");
  await page.getByLabel("Email").fill(opts.email ?? `e2e.invitee.${Date.now()}@example.test`);
  if (opts.note) await page.getByLabel("Note (optional)").fill(opts.note);
  await page.getByRole("button", { name: "Confirm booking" }).click();

  await expect(page.getByRole("heading", { name: /your appointment is confirmed/i })).toBeVisible();
  return { chosenLabel };
}

/** Opens S03 for the seeded event and returns its id. */
export async function openEventEditor(page: Page): Promise<string> {
  await page.goto("/app");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  const row = page.locator("li", { hasText: "Intro tutoring" });
  await row.getByRole("button", { name: "Edit" }).click();
  await expect(page).toHaveURL(/\/app\/events\/[^/]+\/edit/);
  return page.url().match(/\/app\/events\/([^/]+)\/edit/)![1];
}
