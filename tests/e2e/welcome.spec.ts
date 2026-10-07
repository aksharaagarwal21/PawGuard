import { expect, test } from "@playwright/test";

import { expectNoAxeViolations } from "./helpers";

/** The instructions page (linked from sign-in): "Let's start" leads to the sign-in page. */
test("the instructions page leads to sign-in", async ({ page }) => {
  await page.goto("/en/welcome");
  await expect(page.getByRole("heading", { level: 1, name: "Welcome to PawGuard 360" })).toBeVisible();
  await expect(page.getByText("Sample accounts, pets and clinics", { exact: true })).toBeVisible();
  await expect(page.getByText("Photo matching is a research preview", { exact: false })).toBeVisible();
  for (const file of ["/demo/sample-dog.jpg", "/demo/sample-certificate.jpg"]) {
    const res = await page.request.get(file);
    expect(res.status(), file).toBe(200);
    expect(res.headers()["content-type"]).toContain("image/jpeg");
  }
  await expectNoAxeViolations(page);
  await page.getByRole("link", { name: "Let's start" }).click();
  await page.waitForURL(/\/en\/sign-in$/);
  await expect(page.getByRole("button", { name: /^Sign in as Priya/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "How to explore" })).toBeVisible();
});
