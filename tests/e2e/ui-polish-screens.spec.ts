import { expect, test, type Page } from "@playwright/test";

import { DEMO, expectNoAxeViolations, signIn } from "./helpers";

/** UI polish review screenshots at 390 px and 1440 px, with accessibility scans and no horizontal scrolling. */
const WIDTHS = [
  ["390", { width: 390, height: 844 }],
  ["1440", { width: 1440, height: 900 }],
] as const;

async function check(page: Page, name: string) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expectNoAxeViolations(page);
  await page.screenshot({ path: `test-results/ui-polish/${name}.png`, fullPage: true });
}

for (const [label, viewport] of WIDTHS) {
  test(`landing page (${label})`, async ({ page }) => {
    test.setTimeout(60_000);
    await page.setViewportSize(viewport);
    await page.goto("/en");
    await expect(page.getByRole("heading", { level: 1, name: "Never miss your pet's vaccination again." })).toBeVisible();
    await expect(page.getByRole("heading", { name: "What the colours mean" })).toBeVisible();
    await expect(page.getByText("This doesn't mean your pet is unvaccinated.", { exact: false })).toBeVisible();
    await page.getByText("Do reminders send SMS?").click();
    await expect(page.getByText("nothing is sent", { exact: false })).toBeVisible();
    await check(page, `landing-${label}`);
  });
}

for (const [label, viewport] of WIDTHS) {
  test(`get started page (${label})`, async ({ page }) => {
    test.setTimeout(60_000);
    await page.setViewportSize(viewport);
    await page.goto("/en/welcome");
    await expect(page.getByRole("heading", { level: 1, name: /Before you begin/ })).toBeVisible();
    await page.getByText("I work at a vet clinic").click();
    await expect(page.getByText("Next: choose “Sign in as Dr Kiran”.")).toBeVisible();
    await expect(page.getByRole("link", { name: "Let's start — continue to sign in" })).toBeVisible();
    await page.getByText("I have a pet").click();
    await check(page, `get-started-${label}`);
  });
}
