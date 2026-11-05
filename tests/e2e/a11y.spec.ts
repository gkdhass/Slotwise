import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import {
  bookThroughUi,
  bookViaApi,
  openEventEditor,
  slotsForDate,
  upcomingWeekday,
  OWNER,
} from "./helpers";

/**
 * NFR-02 coverage: WCAG 2.2 AA at both ends of the supported range.
 *
 *  - axe on every screen (S01-S11) at 390 px and 1440 px
 *  - a contrast audit of every rendered text/background pair at both widths,
 *    with the measured ratios written to docs/a11y/
 *  - a keyboard-only run of the whole core loop (no mouse events)
 *  - reflow: no horizontal overflow at 390/768/1024/1440 and at 200% zoom
 */

const VIEWPORTS = [
  { id: "390", width: 390, height: 844 },
  { id: "1440", width: 1440, height: 900 },
] as const;

// 200% zoom on a 1280x720 window leaves 640x360 CSS pixels (WCAG 1.4.10 reflow).
const ZOOM_200 = { id: "640x360 (200% of 1280x720)", width: 640, height: 360 };

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

type ScreenSpec = { id: string; name: string; visit: () => Promise<void> };

/**
 * Every screen, reachable independently so each can be scanned at any viewport.
 * Weeks are spaced out so the bookings these walks create never collide with the
 * behavioural specs or with each other.
 */
function buildScreens(page: Page, request: APIRequestContext, week: number, manageToken: string): ScreenSpec[] {
  const date = upcomingWeekday(week);
  return [
    {
      id: "S01",
      name: "sign in",
      visit: async () => {
        await page.goto("/login");
        await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
      },
    },
    {
      id: "S02",
      name: "dashboard",
      visit: async () => {
        await page.goto("/app");
        await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
      },
    },
    {
      id: "S03",
      name: "event editor",
      visit: async () => {
        await openEventEditor(page);
        await expect(page.getByRole("heading", { name: "Event editor" })).toBeVisible();
      },
    },
    {
      id: "S04",
      name: "availability",
      visit: async () => {
        await openEventEditor(page);
        await page.getByRole("button", { name: "Availability" }).click();
        await expect(page.getByRole("heading", { name: "Availability" })).toBeVisible();
        await expect(page.getByLabel("Mon start")).toBeVisible();
      },
    },
    {
      id: "S05",
      name: "preview and publish",
      visit: async () => {
        await openEventEditor(page);
        await page.getByRole("button", { name: "Preview" }).click();
        await expect(page.getByRole("heading", { name: "Preview and publish" })).toBeVisible();
        await expect(page.getByTestId("policy-preview")).toBeVisible();
      },
    },
    {
      id: "S06",
      name: "public event",
      visit: async () => {
        await page.goto("/book/intro-tutoring");
        await expect(page.getByRole("heading", { name: "Intro tutoring" })).toBeVisible();
        await expect(page.getByTestId("policy-public")).toBeVisible();
      },
    },
    {
      id: "S07",
      name: "slot selector",
      visit: async () => {
        await page.goto("/book/intro-tutoring/slots");
        await page.getByLabel("Date").fill(date);
        await expect(page.locator("button[aria-pressed]").first()).toBeVisible();
        await page.locator("button[aria-pressed]").first().click();
        await expect(page.locator("button[aria-pressed]").first()).toHaveAttribute("aria-pressed", "true");
      },
    },
    {
      id: "S08",
      name: "invitee details",
      visit: async () => {
        const slots = await slotsForDate(request, date);
        expect(slots.length).toBeGreaterThan(0);
        await page.goto(`/book/intro-tutoring/details?start=${encodeURIComponent(slots[0].startAt)}`);
        await expect(page.getByRole("heading", { name: "Your details" })).toBeVisible();
        await page.getByLabel("Name").fill("Axe Invitee");
      },
    },
    {
      id: "S09",
      name: "confirmation",
      visit: async () => {
        await bookThroughUi(page, { date, index: 0, name: "Axe Confirmed" });
        await expect(page.getByRole("heading", { name: /your appointment is confirmed/i })).toBeVisible();
      },
    },
    {
      id: "S10",
      name: "manage booking",
      visit: async () => {
        await page.goto(`/manage/${manageToken}`);
        await expect(page.getByRole("heading", { name: "Manage booking" })).toBeVisible();
        // Reschedule panel open: it adds the date field and the slot grid.
        await page.getByRole("button", { name: "Reschedule" }).click();
        await expect(page.getByLabel(/New date/)).toBeVisible();
      },
    },
    {
      id: "S11",
      name: "booking list",
      visit: async () => {
        await page.goto("/app/bookings");
        await expect(page.getByRole("heading", { name: "Bookings" })).toBeVisible();
        await expect(page.getByLabel("Status")).toBeVisible();
      },
    },
  ];
}

function violationMessage(screen: ScreenSpec, viewport: string, violations: unknown[]): string {
  return `${screen.id} ${screen.name} @ ${viewport}: ${JSON.stringify(violations, null, 2)}`;
}

type ContrastSample = {
  screen: string;
  viewport: string;
  text: string;
  color: string;
  background: string;
  fontSize: number;
  fontWeight: number;
  large: boolean;
  ratio: number;
};

/**
 * Measures the real contrast of every rendered text node: computed foreground
 * composited over the nearest non-transparent ancestor background. Large text
 * (>= 24 px, or >= 18.66 px bold) uses the 3:1 AA threshold, everything else 4.5:1.
 */
async function contrastSamples(page: Page, screen: string, viewport: string): Promise<ContrastSample[]> {
  const raw = await page.evaluate(() => {
    type Rgba = { r: number; g: number; b: number; a: number };

    function parse(input: string): Rgba | null {
      const m = input.match(/rgba?\(([^)]+)\)/);
      if (!m) return null;
      const parts = m[1].split(/[,\s/]+/).filter(Boolean).map(Number);
      if (parts.length < 3 || parts.some((n) => Number.isNaN(n))) return null;
      return { r: parts[0], g: parts[1], b: parts[2], a: parts[3] ?? 1 };
    }

    function channel(v: number): number {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    }

    function luminance(c: Rgba): number {
      return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b);
    }

    function ratio(a: Rgba, b: Rgba): number {
      const la = luminance(a);
      const lb = luminance(b);
      return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
    }

    function backgroundOf(el: Element): Rgba {
      let node: Element | null = el;
      while (node) {
        const bg = parse(getComputedStyle(node).backgroundColor);
        if (bg && bg.a > 0.99) return bg;
        node = node.parentElement;
      }
      return { r: 255, g: 255, b: 255, a: 1 };
    }

    const samples: Array<{
      text: string;
      color: string;
      background: string;
      fontSize: number;
      fontWeight: number;
      large: boolean;
      ratio: number;
    }> = [];

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      const text = (node.textContent ?? "").replace(/\s+/g, " ").trim();
      const el = node.parentElement;
      node = walker.nextNode();
      if (!text || !el) continue;

      const style = getComputedStyle(el);
      if (style.visibility === "hidden" || style.display === "none" || Number(style.opacity) === 0) continue;
      if (el.closest("[aria-hidden='true']")) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) continue;

      const fg = parse(style.color);
      if (!fg) continue;
      const bg = backgroundOf(el);
      const composited = {
        r: fg.r * fg.a + bg.r * (1 - fg.a),
        g: fg.g * fg.a + bg.g * (1 - fg.a),
        b: fg.b * fg.a + bg.b * (1 - fg.a),
        a: 1,
      };
      const fontSize = Number.parseFloat(style.fontSize);
      const fontWeight = Number(style.fontWeight) || 400;
      const large = fontSize >= 24 || (fontSize >= 18.66 && fontWeight >= 700);
      samples.push({
        text: text.slice(0, 60),
        color: `rgb(${Math.round(composited.r)}, ${Math.round(composited.g)}, ${Math.round(composited.b)})`,
        background: `rgb(${Math.round(bg.r)}, ${Math.round(bg.g)}, ${Math.round(bg.b)})`,
        fontSize,
        fontWeight,
        large,
        ratio: Math.round(ratio(composited, bg) * 100) / 100,
      });
    }
    return samples;
  });

  return raw.map((s) => ({ ...s, screen, viewport }));
}

for (const viewport of VIEWPORTS) {
  test(`axe and contrast: every screen at ${viewport.id} px`, async ({ page, request }) => {
    test.setTimeout(180_000);
    await page.setViewportSize({ width: viewport.width, height: viewport.height });

    const week = viewport.id === "390" ? 6 : 7;
    const seedDate = upcomingWeekday(week);
    const seedSlots = await slotsForDate(request, seedDate);
    const managed = await bookViaApi(request, seedSlots[seedSlots.length - 1].startAt, {
      name: "Axe Managed",
    });

    const screens = buildScreens(page, request, week, managed.token);
    const violations: string[] = [];
    const contrastFailures: string[] = [];
    const samplesForViewport: ContrastSample[] = [];

    for (const screen of screens) {
      await screen.visit();
      await page.waitForLoadState("networkidle");

      const axe = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
      if (axe.violations.length > 0) violations.push(violationMessage(screen, viewport.id, axe.violations));

      const samples = await contrastSamples(page, `${screen.id} ${screen.name}`, viewport.id);
      // A screen with no measured text would make this audit vacuously pass.
      expect(samples.length, `${screen.id} produced no contrast samples`).toBeGreaterThan(0);
      samplesForViewport.push(...samples);
      for (const sample of samples) {
        const threshold = sample.large ? 3 : 4.5;
        if (sample.ratio < threshold) {
          contrastFailures.push(
            `${screen.id} ${screen.name} @ ${viewport.id}: "${sample.text}" ${sample.color} on ${sample.background} ` +
              `= ${sample.ratio}:1 (needs ${threshold}:1, ${sample.fontSize}px/${sample.fontWeight})`,
          );
        }
      }
    }

    const dir = path.resolve("docs/a11y");
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, `contrast-${viewport.id}.json`), `${JSON.stringify(samplesForViewport, null, 2)}\n`);

    expect(violations, "axe violations").toEqual([]);
    expect(contrastFailures, "text contrast below WCAG 2.2 AA").toEqual([]);
  });
}

test("keyboard-only core loop: sign in, publish path, book, manage and cancel", async ({ page }) => {
  test.setTimeout(180_000);

  /**
   * Tabs until the focused element satisfies `predicate`. No mouse events are
   * used anywhere in this test; `matches()` only receives plain CSS because
   * Playwright's own pseudo-classes are not valid in the page context.
   */
  async function tabUntil(predicate: () => Promise<boolean>, label: string, max = 80) {
    for (let i = 0; i < max; i += 1) {
      await page.keyboard.press("Tab");
      if (await predicate()) return;
    }
    const focused = await page.evaluate(() => document.activeElement?.outerHTML?.slice(0, 140) ?? "none");
    throw new Error(`keyboard: could not reach ${label} (focused: ${focused})`);
  }

  const focusMatches = (selector: string) => () =>
    page.evaluate((sel) => document.activeElement?.matches(sel) ?? false, selector);

  const focusIsButton = (text: string) => () =>
    page.evaluate((t) => {
      const el = document.activeElement as HTMLElement | null;
      return !!el && el.tagName === "BUTTON" && (el.textContent ?? "").trim().startsWith(t);
    }, text);

  // S01: sign in using Tab, typing and Enter only.
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await tabUntil(focusMatches("input[type='email']"), "the email field");
  await page.keyboard.type(OWNER.email);
  await tabUntil(focusMatches("input[type='password']"), "the password field");
  await page.keyboard.type(OWNER.password);
  await tabUntil(focusMatches("button[type='submit']"), "the sign-in button");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  // S02 -> S03: reach the "Edit" action of the seeded event by keyboard.
  await tabUntil(
    () =>
      page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        return (
          !!el &&
          el.tagName === "BUTTON" &&
          (el.textContent ?? "").trim() === "Edit" &&
          (el.closest("li")?.textContent ?? "").includes("Intro tutoring")
        );
      }),
    "Edit on the Intro tutoring row",
  );
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Event editor" })).toBeVisible();
  await expect(page.getByLabel("What should this session be called?")).toHaveValue("Intro tutoring");

  // S03 -> S04: the availability tab is operable by keyboard.
  await tabUntil(focusIsButton("Availability"), "the Availability tab");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Availability" })).toBeVisible();
  await expect(page.locator('input[type="checkbox"]:checked')).toHaveCount(5);

  // S06: the invitee side, entered by URL (browser chrome, not app UI).
  const date = upcomingWeekday(8);
  await page.goto("/book/intro-tutoring");
  await tabUntil(focusIsButton("Choose a time"), "the Choose a time button");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Choose a time" })).toBeVisible();

  // S07: the native date input accepts typed digits; the grid then offers slots.
  await tabUntil(focusMatches("#slot-date"), "the date field");
  const [y, m, d] = date.split("-");
  await page.keyboard.type(`${m}${d}${y}`);
  await expect(page.locator("#slot-date")).toHaveValue(date);
  const slotButtons = page.locator("button[aria-pressed]");
  // Let the grid for the new date finish loading: tabbing while React replaces
  // the list would drop focus and the following Enter would go nowhere.
  await expect(page.getByText("Loading slots…")).toHaveCount(0);
  await page.waitForLoadState("networkidle");
  await expect(slotButtons.first()).toBeVisible();

  // Select the first slot with the keyboard, then Continue.
  await tabUntil(focusMatches("button[aria-pressed]"), "the first slot button");
  await page.keyboard.press("Enter");
  await expect(page.locator("button[aria-pressed='true']")).toHaveCount(1);
  await tabUntil(focusIsButton("Continue"), "the Continue button");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Your details" })).toBeVisible();

  // S08: fill the form by keyboard and submit with Enter.
  await tabUntil(focusMatches("#input-name"), "the name field");
  await page.keyboard.type("Keyboard Invitee");
  await tabUntil(focusMatches("#input-email"), "the email field");
  await page.keyboard.type("keyboard.invitee@example.test");
  await tabUntil(focusMatches("button[type='submit']"), "the confirm button");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: /your appointment is confirmed/i })).toBeVisible();

  // S09 -> S10: open the management view by keyboard.
  await tabUntil(focusIsButton("Manage booking"), "the Manage booking button");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Manage booking" })).toBeVisible();

  // S10: cancel through the confirmation dialog, keyboard only.
  await tabUntil(focusIsButton("Cancel"), "the Cancel button");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await tabUntil(focusIsButton("Cancel booking"), "the Cancel booking confirmation");
  await page.keyboard.press("Enter");
  await expect(page.getByText(/Booking canceled/i)).toBeVisible();
  await expect(page.getByRole("button", { name: "Cancel", exact: true })).toHaveCount(0);

  // The same booking is now read-only: no reschedule affordance for a canceled one.
  await expect(page.getByRole("button", { name: "Reschedule" })).toHaveCount(0);
});

test("reflow: no horizontal overflow at 390/768/1024/1440 and at 200% zoom", async ({ page, request }) => {
  test.setTimeout(240_000);

  const sizes = [
    { id: "390", width: 390, height: 844 },
    { id: "768", width: 768, height: 1024 },
    { id: "1024", width: 1024, height: 768 },
    { id: "1440", width: 1440, height: 900 },
    ZOOM_200,
  ];

  const week = 9;
  const seedDate = upcomingWeekday(week);
  const seedSlots = await slotsForDate(request, seedDate);
  const managed = await bookViaApi(request, seedSlots[seedSlots.length - 1].startAt, { name: "Reflow Managed" });
  const screens = buildScreens(page, request, week, managed.token);

  for (const size of sizes) {
    await page.setViewportSize({ width: size.width, height: size.height });
    for (const screen of screens) {
      await screen.visit();
      await page.waitForLoadState("networkidle");
      const overflow = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
        widest: (() => {
          let worst = { tag: "", width: 0, text: "" };
          for (const el of Array.from(document.body.querySelectorAll("*"))) {
            const rect = el.getBoundingClientRect();
            if (rect.right > document.documentElement.clientWidth + 1 && rect.width > worst.width) {
              worst = {
                tag: el.tagName.toLowerCase(),
                width: Math.round(rect.width),
                text: (el.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 40),
              };
            }
          }
          return worst;
        })(),
      }));
      expect(
        overflow.scrollWidth,
        `${screen.id} ${screen.name} overflows horizontally at ${size.id}: ` +
          `scrollWidth ${overflow.scrollWidth} > clientWidth ${overflow.clientWidth}; ` +
          `widest element ${overflow.widest.tag} (${overflow.widest.width}px) "${overflow.widest.text}"`,
      ).toBeLessThanOrEqual(overflow.clientWidth + 1);
    }
  }
});
