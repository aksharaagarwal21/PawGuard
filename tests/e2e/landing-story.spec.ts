import { expect, test } from "@playwright/test";

import { expectNoAxeViolations } from "./helpers";

/** Opening the site shows the bite story; it steps to the symptoms and to what to do, then on to sign-in. */
test("landing story: bite, what rabies can do, what to do next, sign in", async ({ page }) => {
  await page.goto("/");
  await page.waitForURL(/\/en$/);
  await expect(page.getByRole("heading", { level: 1, name: "One second with a sleeping dog. Know what to do next." })).toBeVisible();
  await page.getByRole("button", { name: "Pause" }).click();
  await expectNoAxeViolations(page);

  await page.getByRole("button", { name: "Go to scene 4" }).click();
  await expect(page.getByText("Startled awake, the dog bites his hand.", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Next scene" }).click();
  const symptoms = page.getByTestId("story-symptoms");
  await expect(symptoms).toContainText("Fear of water and of fresh air");
  await expect(symptoms).toContainText("World Health Organization");

  await page.getByRole("button", { name: "Next scene" }).click();
  await expect(page.getByTestId("story-actions")).toContainText("15 minutes");
  await page.getByRole("link", { name: "What to do now" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "If a dog bites — what to do next" })).toBeInViewport();
  await expect(page.getByTestId("first-aid")).toBeVisible();

  await page.getByRole("link", { name: "Sign in to PawGuard" }).click();
  await page.waitForURL(/\/en\/sign-in$/);
});

test("with reduced motion the story waits for the viewer", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce" });
  const page = await context.newPage();
  await page.goto("/en");
  await expect(page.getByRole("button", { name: "Play" })).toBeVisible();
  await page.waitForTimeout(4000);
  await expect(page.getByText("Scene 1 of 6")).toBeVisible();
  await context.close();
});
