import { expect, test } from "@playwright/test";

import { DEMO, expectNoAxeViolations, signIn } from "./helpers";

/** Owner opens the QR card, the public page shows verified vaccinations only, and a new QR revokes the old link. */
test("vaccination card: QR, public page, PDF and regenerate", async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, DEMO.owner.email);
  await page.getByRole("link", { name: /Bruno/ }).first().click();
  await page.getByRole("link", { name: "Vaccination card (QR)" }).click();
  await expect(page.getByRole("heading", { name: "Vaccination card", level: 1 })).toBeVisible();
  await expect(page.getByRole("img", { name: /QR code/ })).toBeVisible();
  await expectNoAxeViolations(page);
  await page.screenshot({ path: "test-results/pets/phone-card-owner.png", fullPage: true });
  const link = (await page.getByRole("link", { name: /\/card\// }).textContent())!.trim();

  const pdf = await page.request.get((await page.getByRole("link", { name: "Download PDF" }).getAttribute("href"))!);
  expect(pdf.status()).toBe(200);
  expect((await pdf.body()).subarray(0, 4).toString()).toBe("%PDF");

  const visitor = await context.browser()!.newContext({ viewport: { width: 390, height: 844 } });
  const pub = await visitor.newPage();
  await pub.goto(link);
  await expect(pub.getByText("Bruno").first()).toBeVisible();
  await expect(pub.getByText("Up to date")).toBeVisible();
  await expect(pub.getByText("This card shows recorded vaccinations. It is not a health guarantee.")).toBeVisible();
  await expect(pub.getByText("Neha")).toHaveCount(0);
  await expectNoAxeViolations(pub);
  await pub.screenshot({ path: "test-results/pets/phone-card-public.png", fullPage: true });

  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "New QR code" }).click();
  await expect(page.getByText("New QR code made. The old one no longer works.")).toBeVisible();
  await pub.goto(link);
  await expect(pub.getByText("This card is not available")).toBeVisible();
  await visitor.close();
});
