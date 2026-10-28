import { test, expect } from "@playwright/test";
import { login, OWNER, slotsForDate, upcomingWeekday } from "./helpers";

// Public pages must work with no session at all.
test.use({ storageState: { cookies: [], origins: [] } });

test("S01 signs in through the real API and lands on the dashboard", async ({ page }) => {
  await login(page);
  await expect(page.getByRole("button", { name: "Set up a session" })).toBeVisible();
});

test("S01 rejects wrong credentials without navigating away", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(OWNER.email);
  await page.getByLabel("Password").fill("definitely-not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

test("S06 shows the published event, its duration, host zone and policy", async ({ page }) => {
  await page.goto("/book/intro-tutoring");
  await expect(page.getByRole("heading", { name: "Intro tutoring" })).toBeVisible();
  await expect(page.getByText(/30 minutes/i)).toBeVisible();
  await expect(page.getByText(/Times are shown in Asia\/Kolkata/i)).toBeVisible();
  await expect(page.getByTestId("policy-public")).toContainText(/cancel or reschedule/i);
  await expect(page.getByRole("button", { name: "Choose a time" })).toBeVisible();
});

test("S06 shows a generic unavailable page for an unknown slug", async ({ page }) => {
  await page.goto("/book/does-not-exist");
  await expect(page.getByRole("heading", { name: "Unavailable" })).toBeVisible();
});

test("S07 lists real slots in the host time zone and blocks Continue until one is chosen", async ({ page, request }) => {
  const date = upcomingWeekday(8);
  const expected = await slotsForDate(request, date);
  expect(expected.length).toBeGreaterThan(0);

  await page.goto("/book/intro-tutoring/slots");
  await expect(page.getByRole("heading", { name: "Choose a time" })).toBeVisible();
  await page.getByLabel("Date").fill(date);

  const slotButtons = page.locator("button[aria-pressed]");
  await expect(slotButtons).toHaveCount(expected.length);
  await expect(page.getByRole("button", { name: "Continue" })).toBeDisabled();

  await slotButtons.first().click();
  await expect(page.getByRole("button", { name: "Continue" })).toBeEnabled();
});

test("S07 drops the previous day's slots and selection when the date changes", async ({ page, request }) => {
  const firstDate = upcomingWeekday(8);
  const secondDate = upcomingWeekday(9);
  const secondSlots = await slotsForDate(request, secondDate);
  expect(secondSlots.length).toBeGreaterThan(0);

  await page.goto("/book/intro-tutoring/slots");
  const slotButtons = page.locator("button[aria-pressed]");
  await page.getByLabel("Date").fill(firstDate);
  await expect(slotButtons.first()).toBeVisible();
  await slotButtons.first().click();
  await expect(page.locator('button[aria-pressed="true"]')).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Continue" })).toBeEnabled();

  // Changing the date invalidates the choice. While the new list loads, the old
  // buttons must not remain clickable — a click on a stale slot used to survive
  // into a list that no longer contained it — and Continue must go back to
  // disabled until a slot from the new day is chosen.
  await page.getByLabel("Date").fill(secondDate);
  await expect(page.getByRole("button", { name: "Continue" })).toBeDisabled();
  await expect(slotButtons).toHaveCount(secondSlots.length);
  await expect(page.locator('button[aria-pressed="true"]')).toHaveCount(0);
});

test("S10 shows a generic denial for an unknown management token", async ({ page }) => {
  await page.goto(`/manage/${"f".repeat(64)}`);
  await expect(page.getByRole("heading", { name: "Booking unavailable" })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText(/invalid or expired/i);
});
