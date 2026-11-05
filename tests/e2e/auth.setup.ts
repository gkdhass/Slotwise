import { test as setup, expect } from "@playwright/test";
import { login } from "./helpers";

/**
 * Logs in once through the real API and stores the session cookies so every
 * other test starts authenticated. Keeps the login rate limit untouched.
 */
setup("authenticate as the seeded E2E owner", async ({ page }) => {
  await login(page);
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await page.context().storageState({ path: "tests/e2e/.auth/owner.json" });
});
