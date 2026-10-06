import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { DEMO, expectNoAxeViolations, signIn } from "./helpers";

/**
 * Phase 7 — photo lookup in a DEMO organisation with the research-preview identity model: the page is labelled as
 * research, suggestions show photos side by side with no percentage, and nothing is linked until the person
 * confirms. Uses a licence-filtered COCO dog photo (the same picture is enrolled first), so this checks the
 * integration — not identification accuracy. Skipped when the preview model or the COCO sample is not set up.
 */
test.describe.configure({ mode: "serial" });
test.skip(({ isMobile }) => isMobile, "desktop only");
test.setTimeout(240_000); // validation + detection + enrolment + search on CPU

const ROOT = path.resolve(import.meta.dirname, "../..");
const MANIFEST = path.join(ROOT, "data/manifests/coco-val2017-dog-sample-v1.json");

function cocoDogImage(): string | null {
  if (!fs.existsSync(MANIFEST)) return null;
  const m = JSON.parse(fs.readFileSync(MANIFEST, "utf8")) as { images: { file_name: string; split: string; dog_boxes_xywh: number[][] }[] };
  const e = m.images.find((i) => i.split === "verification" && i.dog_boxes_xywh.length === 1);
  return e ? path.join(ROOT, "data/raw/coco/val2017_sample", e.file_name) : null;
}

test("photo lookup suggests possible matches and links only after confirmation", async ({ page }) => {
  const img = cocoDogImage();
  test.skip(!img || !fs.existsSync(img), "COCO sample not available");
  await signIn(page, DEMO.volunteer.email);
  const status = await (await page.context().request.get("/api/v1/identity/status")).json();
  test.skip(status.mode !== "research_preview", "research-preview identity model not enabled in this environment");

  // Enrol: record the photo (chosen subject) as a sighting of the first animal in the registry.
  await page.goto("/en/app/animals");
  await page.locator("main ul li a").first().click();
  await page.waitForURL(/\/app\/animals\/[0-9a-f-]{36}/);
  const animalId = page.url().split("?")[0]!.split("/").pop()!;
  const reference = (await page.locator("main").getByText(/PG-[0-9A-Z]{4}-[0-9A-Z]{4}/).first().innerText()).match(/PG-[0-9A-Z]{4}-[0-9A-Z]{4}/)![0];
  await page.getByRole("link", { name: "Add sighting" }).click();
  await page.getByTestId("sighting-photo-file-input").setInputFiles(img!);
  await expect(page.getByText("Dog 1", { exact: true })).toBeVisible({ timeout: 90_000 });
  await page.getByText("Dog 1", { exact: true }).click();
  const reason = page.getByLabel("Why use this photo anyway?");
  if (await reason.count()) await reason.fill("Best photo available");
  await page.getByRole("button", { name: "Save sighting" }).click();
  await page.waitForURL(/tab=sightings/);
  // Wait until the gallery index has caught up (enrolment runs in the background worker).
  await expect(async () => {
    const s = await (await page.context().request.get("/api/v1/identity/status")).json();
    expect(s.index_coverage).toBe(1);
  }).toPass({ timeout: 120_000 });

  // Look up the same picture from the capture page.
  await page.goto("/en/app/capture");
  await expect(page.getByRole("heading", { name: "Find an animal from a photo" })).toBeVisible();
  await expect(page.getByText("Research preview — not validated")).toBeVisible();
  await page.getByTestId("lookup-photo-file-input").setInputFiles(img!);
  await expect(page.getByText("Dog 1", { exact: true })).toBeVisible({ timeout: 90_000 });
  await page.getByText("Dog 1", { exact: true }).click();
  const reason2 = page.getByLabel("Why use this photo anyway?");
  if (await reason2.count()) await reason2.fill("Best photo available");
  await page.getByRole("button", { name: "Look for possible matches" }).click();
  await expect(page.getByRole("heading", { name: "Possible matches" })).toBeVisible({ timeout: 90_000 });
  const main = page.getByRole("main");
  await expect(main.getByText("Compare carefully before deciding")).toBeVisible();
  await expect(main.getByText(reference).first()).toBeVisible();
  await expect(main.getByText("Your photo").first()).toBeVisible();
  expect(await main.innerText()).not.toMatch(/\d+\s?%/); // no percentages anywhere
  await expectNoAxeViolations(page);
  await page.screenshot({ path: path.join(ROOT, "docs/screenshots/phase7/lookup-candidates-1440.png"), fullPage: true });

  // Nothing is linked until confirmed.
  const card = main.getByRole("listitem").filter({ hasText: reference }).first();
  await card.getByRole("button", { name: "This is the same animal" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText(`Record this photo as a sighting of ${reference}?`)).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await card.getByRole("button", { name: "This is the same animal" }).click();
  await dialog.getByRole("button", { name: "Yes, same animal" }).click();
  await page.waitForURL(new RegExp(`/app/animals/${animalId}\\?tab=sightings`));
  const feedback = await (await page.context().request.get("/api/v1/identity/feedback")).json();
  expect(feedback.decisions).toBeGreaterThan(0);
});
