import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("core loop smoke: public event page renders", async ({ page }) => {
  await page.goto("/book/intro-tutoring");
  await expect(page.getByRole("heading", { name: /intro tutoring/i })).toBeVisible();
});

test("axe: S06 public event page", async ({ page }) => {
  await page.goto("/book/intro-tutoring");
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("axe: S07 slot selector", async ({ page }) => {
  await page.goto("/book/intro-tutoring/slots");
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("axe: S08 invitee details", async ({ page }) => {
  await page.goto("/book/intro-tutoring/details?start=2026-11-02T04:30:00.000Z");
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("axe: S09 confirmation (loading state)", async ({ page }) => {
  await page.goto("/booking/confirmed/demo-ref");
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});