import { expect, test } from "@playwright/test";

import { DEMO, expectNoAxeViolations, signIn } from "./helpers";

/** Notification settings (owner) and the Messages panel (clinic) at 390 px and 1440 px. */
for (const [label, viewport] of [
  ["390", { width: 390, height: 844 }],
  ["1440", { width: 1440, height: 900 }],
] as const) {
  test(`notification screens (${label})`, async ({ page }) => {
    test.setTimeout(60_000);
    await page.setViewportSize(viewport);
    await signIn(page, DEMO.owner.email);
    await page.goto("/en/app/reminders");
    await page.getByRole("link", { name: "Choose how to get reminders" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Notifications" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Email" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Browser notifications" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "WhatsApp" })).toBeVisible();
    await expect(page.getByText("In this demo")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await expectNoAxeViolations(page);
    await page.screenshot({ path: `test-results/notify/settings-${label}.png`, fullPage: true });

    await page.context().clearCookies();
    await signIn(page, DEMO.clinicVet.email);
    await page.goto("/en/app/clinic");
    await expect(page.getByRole("heading", { name: "Messages" })).toBeVisible();
    await expectNoAxeViolations(page);
    await page.locator("section", { has: page.getByRole("heading", { name: "Messages" }) }).screenshot({
      path: `test-results/notify/messages-${label}.png`,
    });
  });
}

test("assistant page explains when it is not set up, and owners find it in the menu", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await signIn(page, DEMO.owner.email);
  await page.getByRole("link", { name: "Ask PawGuard" }).first().click();
  await expect(page.getByRole("heading", { level: 1, name: "Ask PawGuard" })).toBeVisible();
  await expect(page.getByText("The assistant isn't set up")).toBeVisible();
  await expectNoAxeViolations(page);
});
