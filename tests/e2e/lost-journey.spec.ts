import { expect, test } from "@playwright/test";

import { DEMO, expectNoAxeViolations, signIn } from "./helpers";

test.skip(({ isMobile }) => isMobile, "journey changes demo data, so it runs once (desktop project; it covers 390 px itself)");

/**
 * Lost pet: the owner reports Bruno lost → a finder (no account) scans the QR card and writes privately → the owner
 * replies in Lost & found → the finder reads it on their private link → the owner marks Bruno found.
 */
test("lost pet: report, finder message, private reply, found", async ({ page, browser }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, DEMO.owner.email);
  await page.getByRole("link", { name: /Bruno/ }).first().click();
  await page.getByText("Report Bruno lost").click();
  await page.getByLabel(/Where \(area in words\)/).fill("Near the park gate");
  await page.getByRole("button", { name: "Report lost" }).click();
  await expect(page.getByRole("heading", { name: "Bruno is reported lost" })).toBeVisible();
  await page.getByRole("link", { name: "Vaccination card (QR)" }).click();
  const cardUrl = (await page.getByRole("link", { name: /\/card\// }).textContent())!.trim();

  // A finder with no account opens the QR card.
  const finderCtx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const finder = await finderCtx.newPage();
  await finder.goto(cardUrl);
  await expect(finder.getByRole("heading", { name: /Bruno is lost/ })).toBeVisible();
  await expect(finder.getByText("Near the park gate", { exact: false })).toBeVisible();
  await expectNoAxeViolations(finder);
  await finder.getByLabel("Your message to the owner").fill("I think I saw Bruno near the market at 5 pm.");
  await finder.getByRole("button", { name: "Send to the owner" }).click();
  await expect(finder.getByText("Sent to the owner — thank you!")).toBeVisible();
  const privateLink = (await finder.getByRole("link", { name: /\/found\// }).textContent())!.trim();
  await finder.screenshot({ path: "test-results/lost/finder-card-390.png", fullPage: true });

  // The owner reads and replies.
  await page.goto("/en/app/lost");
  await expect(page.getByText("I think I saw Bruno near the market at 5 pm.")).toBeVisible();
  await page.getByPlaceholder("Write a message…").fill("Thank you! Is he still there?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Thank you! Is he still there?")).toBeVisible();
  await expectNoAxeViolations(page);
  await page.screenshot({ path: "test-results/lost/owner-lost-390.png", fullPage: true });

  // The finder sees the reply on the private link; the owner's details are not on the page.
  await finder.goto(privateLink);
  await expect(finder.getByText("Thank you! Is he still there?")).toBeVisible();
  await expect(finder.getByText("Neha")).toHaveCount(0);
  await finder.getByPlaceholder("Write a message…").fill("Yes, I'm waiting with him.");
  await finder.getByRole("button", { name: "Send" }).click();
  await expect(finder.getByText("Yes, I'm waiting with him.")).toBeVisible();

  // Found: the conversation closes for the finder.
  await page.goto("/en/app/lost");
  await page.getByRole("button", { name: "Mark found" }).first().click();
  await expect(page.getByText("Found", { exact: true }).first()).toBeVisible();
  await finder.reload();
  await expect(finder.getByText("Found — thank you!")).toBeVisible();
  await finderCtx.close();
});
