import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { DEMO, signIn } from "./helpers";

/**
 * Full pet vaccination journey on the seeded demo data (run after `pawguard-admin demo-reset --yes`):
 * owner marks Coco's overdue reminder done with a certificate → the clinic vet verifies it in the existing workbench
 * with a next due date → the owner sees "Up to date" and the reminder is gone → the vet moves the demo date and the
 * clinic dashboard shows Misty due this week.
 */
test.skip(({ isMobile }) => isMobile, "journey changes demo data, so it runs once (desktop project; it covers 390 px itself)");

const CERT = path.resolve(import.meta.dirname, "../fixtures/synthetic-certificate.jpg");

function inDays(days: number): string {
  const d = new Date(Date.now() + days * 86_400_000);
  return d.toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
}

async function signOut(page: Page) {
  await page.context().clearCookies();
}

test("owner marks a reminder done, vet verifies, status and reminders update", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 390, height: 844 });

  // 1. Owner: Coco is overdue; mark the reminder done with the certificate.
  await signIn(page, DEMO.owner.email);
  const coco = page.getByRole("listitem").filter({ hasText: "Coco" });
  await expect(coco.getByText("Overdue", { exact: true })).toBeVisible();
  await page.goto("/en/app/reminders");
  const card = page.locator("li").filter({ hasText: "Coco" }).filter({ hasText: "Overdue" }).first();
  await card.getByRole("button", { name: "Mark as done" }).click();
  await card.locator('[data-testid$="-cert-file-input"]').setInputFiles(CERT);
  // The upload must finish before the form accepts it; retry the submit until it is saved.
  await expect(async () => {
    await card.getByRole("button", { name: "Mark as done" }).last().click();
    await expect(page.getByText("Saved. The clinic's vet will check the certificate.")).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 30_000 });
  await page.reload();
  await expect(page.locator("li").filter({ hasText: "Coco" }).filter({ hasText: "Overdue" })).toHaveCount(0);
  await page.goto("/en/app/pets");
  await expect(coco.getByText("Overdue", { exact: true })).toBeVisible(); // unverified does not clear it
  await expect(coco.getByText(/waiting for the clinic's vet/)).toBeVisible();
  await signOut(page);

  // 2. Clinic vet: dashboard → review the owner's upload → verify with a next due date.
  await page.setViewportSize({ width: 1440, height: 900 });
  await signIn(page, DEMO.clinicVet.email);
  await page.goto("/en/app/clinic");
  await expect(page.getByText(/of 3 registered pets up to date/)).toBeVisible();
  await expect(page.getByText("Based on pets registered in this app — not population coverage.")).toBeVisible();
  const awaiting = page.locator("section", { has: page.getByRole("heading", { name: /Awaiting verification/ }) });
  await awaiting.locator("li").filter({ hasText: "Coco" }).getByRole("link", { name: "Review" }).click();
  await expect(page.getByText("Entered by the pet owner (unverified)").first()).toBeVisible();
  await page.getByRole("button", { name: "Verify" }).first().click();
  await page.getByLabel(/Next due date/).fill(inDays(365));
  await page.getByRole("dialog").getByRole("button", { name: "Verify" }).click();
  await expect(page).toHaveURL(/done=verified/);

  // 3. Demo date: +7 days puts Misty (due in 10 days) in "Due this week".
  await page.goto("/en/app/clinic");
  const week = page.locator("section", { has: page.getByRole("heading", { name: /Due this week/ }) });
  await expect(week.getByText("Misty")).toHaveCount(0);
  await page.getByRole("button", { name: "+7 days" }).click();
  await expect(week.getByText("Misty")).toBeVisible();
  await page.getByRole("button", { name: "Back to the real date" }).click();
  await expect(page.getByText(/real date/).first()).toBeVisible();
  await signOut(page);

  // 4. Owner: Coco is now up to date, verified by the vet, and the overdue reminder is gone.
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, DEMO.owner.email);
  await expect(coco.getByText("Up to date", { exact: true })).toBeVisible();
  await coco.getByRole("link").first().click();
  await expect(page.getByText("Verified by vet").first()).toBeVisible();
  await expect(page.getByText("Due date set by the vet.").first()).toBeVisible();
  await page.goto("/en/app/reminders");
  await expect(page.locator("li").filter({ hasText: "Coco" })).toHaveCount(0);
});
