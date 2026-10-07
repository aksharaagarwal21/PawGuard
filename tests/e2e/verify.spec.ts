import { expect, test, type Page } from "@playwright/test";

import { expectNoAxeViolations } from "./helpers";

/** Public certificate verifier: genuine / altered / cancelled samples, honesty note, and checking with no network. */

async function sampleTexts(page: Page): Promise<Record<"genuine" | "altered" | "cancelled", string>> {
  await page.goto("/en/verify/samples");
  const out: Record<string, string> = {};
  for (const key of ["genuine", "altered", "cancelled"] as const) {
    const t = await page.getByTestId(`sample-${key}`).locator("[data-qr-text]").textContent();
    expect(t?.startsWith("PG1:")).toBe(true);
    out[key] = (t ?? "").trim();
  }
  return out as Record<"genuine" | "altered" | "cancelled", string>;
}

async function check(page: Page, qr: string) {
  await page.getByLabel("Or paste the code text").fill(qr);
  await page.getByRole("button", { name: "Check", exact: true }).click();
  return page.getByTestId("verify-result");
}

test("genuine, altered and cancelled certificates, verified in the browser", async ({ page }) => {
  const samples = await sampleTexts(page);
  await page.goto("/en/verify");
  await expect(page.getByRole("heading", { level: 1, name: "Verify a vaccination certificate" })).toBeVisible();
  await expect(page.getByTestId("lists-freshness")).toContainText("Trust list and cancellations last updated");
  await expect(page.getByRole("link", { name: "Verify a certificate" }).first()).toBeVisible(); // header link

  const genuine = await check(page, samples.genuine);
  await expect(genuine.locator("[data-result=genuine]")).toBeVisible();
  await expect(genuine).toContainText("Issued by Demo — Lotus Pet Clinic");
  await expect(genuine).toContainText("Bruno");
  await expect(genuine).toContainText("Check that this matches the animal in front of you.");

  const altered = await check(page, samples.altered);
  await expect(altered.locator("[data-result=altered]")).toBeVisible();
  await expect(altered).toContainText("This certificate was changed or wasn't issued by a registered clinic.");

  const cancelled = await check(page, samples.cancelled);
  await expect(cancelled.locator("[data-result=revoked]")).toBeVisible();
  await expect(cancelled).toContainText("replaced or cancelled by the clinic");

  const junk = await check(page, "https://example.org/not-a-certificate");
  await expect(junk.locator("[data-result=unreadable]")).toBeVisible();

  await expect(page.getByText("It does not confirm the pet's health.")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expectNoAxeViolations(page);
});

test("verification works with the network switched off after one visit", async ({ page, context }) => {
  test.setTimeout(90_000);
  const samples = await sampleTexts(page);
  await page.goto("/en/verify");
  await expect(page.getByTestId("lists-freshness")).toContainText("last updated");
  // Wait until the service worker controls the page and the page itself is stored for offline use.
  await page.waitForFunction(async () => {
    await navigator.serviceWorker.ready;
    return Boolean(await caches.match(location.pathname));
  }, null, { timeout: 30_000 });
  await page.reload(); // second load goes through the service worker, which stores every asset it serves
  await expect(page.getByTestId("lists-freshness")).toContainText("last updated");

  await context.setOffline(true);
  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "Verify a vaccination certificate" })).toBeVisible();
  await expect(page.getByText("You're offline")).toBeVisible();
  const genuine = await check(page, samples.genuine);
  await expect(genuine.locator("[data-result=genuine]")).toBeVisible();
  const altered = await check(page, samples.altered);
  await expect(altered.locator("[data-result=altered]")).toBeVisible();
  const cancelled = await check(page, samples.cancelled);
  await expect(cancelled.locator("[data-result=revoked]")).toBeVisible();
  await context.setOffline(false);
});

test("a photo of the QR code is read in the browser (WebAssembly fallback reader)", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/en/verify/samples");
  // Turn the genuine sample's QR (SVG) into a PNG "photo" with a white margin.
  const png = await page.getByTestId("sample-genuine").locator("svg").evaluate(async (svg) => {
    const xml = new XMLSerializer().serializeToString(svg);
    const img = new Image();
    img.src = "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(xml)));
    await img.decode();
    const canvas = document.createElement("canvas");
    canvas.width = 600;
    canvas.height = 600;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, 600, 600);
    ctx.drawImage(img, 50, 50, 500, 500);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  // Arrive through the header link (in-app navigation keeps the first page's security policies).
  await page.goto("/en");
  await page.getByRole("link", { name: "Verify a certificate" }).first().click();
  await page.waitForURL(/\/en\/verify$/);
  await expect(page.getByTestId("lists-freshness")).toContainText("last updated");
  await page.locator('input[type="file"]').setInputFiles({ name: "qr.png", mimeType: "image/png", buffer: Buffer.from(png, "base64") });
  await expect(page.getByTestId("verify-result").locator("[data-result=genuine]")).toBeVisible({ timeout: 30_000 });
});
