import { test, expect } from "@playwright/test";
import {
  bookThroughUi,
  bookViaApi,
  dateInZone,
  openEventEditor,
  slotsForDate,
  upcomingWeekday,
  HOST_TZ,
} from "./helpers";

// Each scenario uses a different week so bookings never collide.
const CORE_LOOP_WEEK = 0;
const CONFLICT_WEEK = 1;
const RESCHEDULE_WEEK = 2;

test.describe("owner core loop", () => {
  test("S02 -> S05: dashboard, editor, availability and preview reflect the real API", async ({ page }) => {
    const id = await openEventEditor(page);
    await expect(page.getByLabel("What should this session be called?")).toHaveValue("Intro tutoring");
    await expect(page.getByLabel("How long should the session last? (minutes)")).toHaveValue("30");
    await expect(page.getByLabel("Time zone (IANA)")).toHaveValue(HOST_TZ);

    // Availability is loaded from the database.
    await page.getByRole("button", { name: "Availability" }).click();
    await expect(page.getByRole("heading", { name: "Availability" })).toBeVisible();
    await expect(page.locator('input[type="checkbox"]:checked')).toHaveCount(5);
    await expect(page.getByLabel("Mon start")).toHaveValue("09:00");

    // Preview shows the published state and the cancellation policy.
    await page.getByRole("button", { name: "Preview" }).click();
    await expect(page.getByRole("heading", { name: "Preview and publish" })).toBeVisible();
    await expect(page.getByTestId("policy-preview")).toContainText(/cancel or reschedule/i);
    await expect(page.getByText(`/book/intro-tutoring`)).toBeVisible();
    await expect(page.getByRole("button", { name: "Published" })).toBeDisabled();

    // Bookings list (S11) is reachable and reads the API.
    await page.goto(`/app/events/${id}/preview`);
    await page.goto("/app/bookings");
    await expect(page.getByRole("heading", { name: "Bookings" })).toBeVisible();
    await expect(page.getByLabel("Status")).toBeVisible();
  });

  test("S06 -> S09 -> S10: book a slot end to end, see both time zones, then cancel", async ({ page }) => {
    const date = upcomingWeekday(CORE_LOOP_WEEK);
    await bookThroughUi(page, { date, index: 0, name: "Core Loop Invitee", note: "Please be on time" });

    // S09 confirmation is only rendered after the API confirmed the booking.
    await expect(page.getByText(/Your time zone: America\/New_York/i)).toBeVisible();
    await expect(page.getByText(/Host time zone:/i)).toBeVisible();
    await expect(page.getByText(new RegExp(`\\(${HOST_TZ}\\)`))).toBeVisible();
    await expect(page.getByText("Intro tutoring", { exact: true })).toBeVisible();
    await expect(page.getByText(/confirmation email with a secure management link/i)).toBeVisible();

    // S09 -> S10 uses the real management token.
    await page.getByRole("button", { name: "Manage booking" }).click();
    await expect(page.getByRole("heading", { name: "Manage booking" })).toBeVisible();
    await expect(page.getByText(/Time zone: America\/New_York/i)).toBeVisible();
    await expect(page.getByText(new RegExp(`\\(${HOST_TZ}\\)`))).toBeVisible();

    // Cancel and confirm the server acknowledged it.
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByRole("button", { name: "Cancel booking" }).click();
    await expect(page.getByText(/Booking canceled/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Cancel", exact: true })).toHaveCount(0);
  });

  test("S06 -> S07 -> S08: a taken slot returns to slot selection with the invitee input preserved", async ({
    page,
    request,
  }) => {
    const date = upcomingWeekday(CONFLICT_WEEK);
    const slots = await slotsForDate(request, date);
    expect(slots.length).toBeGreaterThan(1);

    // Someone else books the first slot before this invitee submits.
    await bookViaApi(request, slots[0].startAt, { name: "First Invitee" });

    await page.goto(`/book/intro-tutoring/details?start=${encodeURIComponent(slots[0].startAt)}`);
    await expect(page.getByRole("heading", { name: "Your details" })).toBeVisible();
    await page.getByLabel("Name").fill("Conflict Carry");
    await page.getByLabel("Email").fill("conflict.carry@example.test");
    await page.getByLabel("Note (optional)").fill("Keep my note");
    await page.getByRole("button", { name: "Confirm booking" }).click();

    // Back on S07 with the conflict message, not a fake success.
    await expect(page).toHaveURL(/\/book\/intro-tutoring\/slots\?conflict=1/);
    await expect(page.getByRole("heading", { name: "Choose a time" })).toBeVisible();
    await expect(page.getByRole("alert")).toContainText(/just taken/i);
    await expect(page.getByRole("alert")).toContainText(/kept/i);

    // The taken slot disappears from the refreshed list.
    const slotButtons = page.locator("button[aria-pressed]");
    await expect(slotButtons.first()).toBeVisible();
    await expect(slotButtons).toHaveCount(slots.length - 1);
    await expect(page.locator("button[aria-pressed]", { hasText: slots[0].label })).toHaveCount(0);

    // Pick another slot: the invitee's name, email and note survive the round trip.
    await slotButtons.first().click();
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByRole("heading", { name: "Your details" })).toBeVisible();
    await expect(page.getByLabel("Name")).toHaveValue("Conflict Carry");
    await expect(page.getByLabel("Email")).toHaveValue("conflict.carry@example.test");
    await expect(page.getByLabel("Note (optional)")).toHaveValue("Keep my note");

    await page.getByRole("button", { name: "Confirm booking" }).click();
    await expect(page.getByRole("heading", { name: /your appointment is confirmed/i })).toBeVisible();
  });

  test("S10 reschedule moves the booking and frees the previous slot", async ({ page, request }) => {
    const hostDate = upcomingWeekday(RESCHEDULE_WEEK);
    const slots = await slotsForDate(request, hostDate);
    expect(slots.length).toBeGreaterThan(1);
    const original = slots[0];
    const destination = slots[1];

    const booked = await bookViaApi(request, original.startAt, {
      name: "Reschedule Rita",
      timezone: "America/New_York",
    });
    await page.goto(`/manage/${booked.token}`);
    await expect(page.getByRole("heading", { name: "Manage booking" })).toBeVisible();

    // The management screen works in the invitee's zone, so the date picker
    // must be set to that zone's calendar date.
    const inviteeTz = "America/New_York";
    const inviteeDate = dateInZone(original.startAt, inviteeTz);
    const inviteeSlots = await slotsForDate(request, inviteeDate, inviteeTz);
    const inviteeDestination = inviteeSlots.find((s) => s.startAt === destination.startAt);
    expect(inviteeDestination, "destination slot should be visible in the invitee zone").toBeTruthy();

    await page.getByRole("button", { name: "Reschedule" }).click();
    await page.getByLabel(/New date/).fill(inviteeDate);

    const destinationButton = page.locator("button[aria-pressed]", { hasText: inviteeDestination!.label });
    await expect(destinationButton).toBeVisible();
    await destinationButton.click();

    await page.getByRole("button", { name: "Confirm reschedule" }).click();
    await expect(page.getByText(/Booking rescheduled/i)).toBeVisible();

    // The old instant is free again and the new one is taken.
    const after = await slotsForDate(request, inviteeDate, inviteeTz);
    expect(after.some((s) => s.startAt === original.startAt)).toBe(true);
    expect(after.some((s) => s.startAt === destination.startAt)).toBe(false);
  });
});

