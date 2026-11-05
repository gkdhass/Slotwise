import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { openEventEditor, SLUG, upcomingWeekday } from "./helpers";

const outputDir = path.resolve("docs/screenshots");
const viewports = [
  { name: "390", width: 390, height: 844, week: 3 },
  { name: "1440", width: 1440, height: 1000, week: 4 },
] as const;

/** Captures the real seeded application, not mocked component snapshots. */
test("M8 captures S01-S11 at mobile and desktop widths", async ({ page }) => {
  test.setTimeout(180_000);
  fs.mkdirSync(outputDir, { recursive: true });

  for (const viewport of viewports) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });

    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await page.screenshot({ path: path.join(outputDir, `S01-${viewport.name}.png`), fullPage: true });

    const eventId = await openEventEditor(page);
    await page.screenshot({ path: path.join(outputDir, `S02-${viewport.name}.png`), fullPage: true });

    await page.goto(`/app/events/${eventId}/edit`);
    await expect(page.getByRole("heading", { name: "Event editor" })).toBeVisible();
    await page.screenshot({ path: path.join(outputDir, `S03-${viewport.name}.png`), fullPage: true });

    await page.goto(`/app/events/${eventId}/availability`);
    await expect(page.getByRole("heading", { name: "Availability" })).toBeVisible();
    await page.screenshot({ path: path.join(outputDir, `S04-${viewport.name}.png`), fullPage: true });

    await page.goto(`/app/events/${eventId}/preview`);
    await expect(page.getByRole("heading", { name: "Preview and publish" })).toBeVisible();
    await page.screenshot({ path: path.join(outputDir, `S05-${viewport.name}.png`), fullPage: true });

    await page.goto(`/book/${SLUG}`);
    await expect(page.getByRole("heading", { name: "Intro tutoring" })).toBeVisible();
    await page.screenshot({ path: path.join(outputDir, `S06-${viewport.name}.png`), fullPage: true });

    await page.getByRole("button", { name: "Choose a time" }).click();
    await expect(page.getByRole("heading", { name: "Choose a time" })).toBeVisible();
    const date = upcomingWeekday(viewport.week);
    const dateInput = page.getByLabel("Date");
    await dateInput.evaluate((element, value) => {
      const input = element as HTMLInputElement;
      // Use the native setter so React's controlled input observes the change
      // while avoiding Playwright's locale-sensitive date-input fill path on
      // Windows.
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      setter?.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }, date);
    await expect(dateInput).toHaveValue(date);
    await expect(page.locator("button[aria-pressed]").first()).toBeVisible();
    await page.screenshot({ path: path.join(outputDir, `S07-${viewport.name}.png`), fullPage: true });

    await page.locator("button[aria-pressed]").first().click();
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByRole("heading", { name: "Your details" })).toBeVisible();
    await page.screenshot({ path: path.join(outputDir, `S08-${viewport.name}.png`), fullPage: true });

    await page.getByLabel("Name").fill(`M8 Screenshot ${viewport.name}`);
    await page.getByLabel("Email").fill(`m8-${viewport.name}-${Date.now()}@example.test`);
    await page.getByRole("button", { name: "Confirm booking" }).click();
    await expect(page.getByRole("heading", { name: /your appointment is confirmed/i })).toBeVisible();
    await page.screenshot({ path: path.join(outputDir, `S09-${viewport.name}.png`), fullPage: true });

    await page.getByRole("button", { name: "Manage booking" }).click();
    await expect(page.getByRole("heading", { name: "Manage booking" })).toBeVisible();
    await page.screenshot({ path: path.join(outputDir, `S10-${viewport.name}.png`), fullPage: true });

    await page.goto("/app/bookings");
    await expect(page.getByRole("heading", { name: "Bookings" })).toBeVisible();
    await page.screenshot({ path: path.join(outputDir, `S11-${viewport.name}.png`), fullPage: true });

    // Keep the screen set explicit so a missing capture fails loudly.
    for (const screen of Array.from({ length: 11 }, (_, index) => index + 1)) {
      expect(fs.existsSync(path.join(outputDir, `S${String(screen).padStart(2, "0")}-${viewport.name}.png`))).toBe(true);
    }
  }
});
