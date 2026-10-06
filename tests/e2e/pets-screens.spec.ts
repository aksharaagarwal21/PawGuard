import { expect, test } from "@playwright/test";

import { DEMO, expectNoAxeViolations, signIn } from "./helpers";

/** Owner screens at phone (390 px) and desktop widths, with automated accessibility checks. */
for (const [label, viewport] of [
  ["phone", { width: 390, height: 844 }],
  ["desktop", { width: 1440, height: 900 }],
] as const) {
  test(`owner screens render without horizontal scroll (${label})`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await signIn(page, DEMO.owner.email);
    await expect(page).toHaveURL(/\/en\/app\/pets$/);
    await expect(page.getByRole("heading", { name: "My pets", level: 1 })).toBeVisible();
    for (const name of ["Bruno", "Misty", "Coco"]) await expect(page.getByText(name, { exact: true })).toBeVisible();
    await expect(page.getByText("Up to date").first()).toBeVisible();
    await expect(page.getByText("Due soon").first()).toBeVisible();
    await expect(page.getByText("Overdue").first()).toBeVisible();
    const noScroll = async () =>
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await noScroll();
    await expectNoAxeViolations(page);
    await page.screenshot({ path: `test-results/pets/${label}-my-pets.png`, fullPage: true });

    await page.getByRole("link", { name: /Coco/ }).first().click();
    await expect(page.getByRole("heading", { name: "Coco", level: 1 })).toBeVisible();
    await expect(page.getByText("Verified by vet").first()).toBeVisible();
    await noScroll();
    await expectNoAxeViolations(page);
    await page.screenshot({ path: `test-results/pets/${label}-pet.png`, fullPage: true });

    await page.goto("/en/app/reminders");
    await expect(page.getByRole("heading", { name: "Reminders", level: 1 })).toBeVisible();
    await page.getByText("Notification preview").first().click();
    await expect(page.getByText("Preview only — no message is actually sent.").first()).toBeVisible();
    await noScroll();
    await expectNoAxeViolations(page);
    await page.screenshot({ path: `test-results/pets/${label}-reminders.png`, fullPage: true });
  });
}
