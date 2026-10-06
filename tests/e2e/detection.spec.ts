import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { DEMO, expectNoAxeViolations, signIn } from "./helpers";

/**
 * Phase 5 — real detector inference reaches the UI: boxes are drawn from returned coordinates, the person chooses
 * the subject (nothing preselected when several dogs), and photo-quality warnings need a reason to continue.
 * Uses a licence-filtered COCO image from the local sample (skipped if the sample has not been built).
 */
test.skip(({ isMobile }) => isMobile, "desktop only");
test.setTimeout(150_000); // includes background validation + analysis on CPU

const ROOT = path.resolve(import.meta.dirname, "../..");
const MANIFEST = path.join(ROOT, "data/manifests/coco-val2017-dog-sample-v1.json");

function cocoImage(dogs: number): string | null {
  if (!fs.existsSync(MANIFEST)) return null;
  const m = JSON.parse(fs.readFileSync(MANIFEST, "utf8")) as { images: { file_name: string; split: string; dog_boxes_xywh: number[][] }[] };
  const e = m.images.find((i) => i.split === "verification" && i.dog_boxes_xywh.length === dogs);
  return e ? path.join(ROOT, "data/raw/coco/val2017_sample", e.file_name) : null;
}

test("a photo with a dog shows a detected box and records the chosen subject", async ({ page }) => {
  const img = cocoImage(1);
  test.skip(!img || !fs.existsSync(img), "COCO sample not available");
  await signIn(page, DEMO.volunteer.email);
  await page.goto("/en/app/animals");
  await page.locator("main ul li a").first().click();
  await page.getByRole("link", { name: "Add sighting" }).click();
  await page.getByTestId("sighting-photo-file-input").setInputFiles(img!);
  await expect(page.getByText(/Is this the dog this record is about\?|Several dogs may be in this photo/)).toBeVisible({ timeout: 60_000 });
  await expect(page.locator("svg rect").first()).toBeAttached();
  await expect(page.getByText("They do not identify the animal", { exact: false })).toBeVisible();
  await page.getByText("Dog 1", { exact: true }).click();
  await expectNoAxeViolations(page);
  const overrideField = page.getByLabel("Why use this photo anyway?");
  if (await overrideField.count()) await overrideField.fill("Best photo available");
  await page.getByRole("button", { name: "Save sighting" }).click();
  await page.waitForURL(/tab=sightings/);
  await expect(page.getByText("1 photo").first()).toBeVisible();
});

test("a very dark photo needs a reason before it can be used", async ({ page }) => {
  await signIn(page, DEMO.volunteer.email);
  await page.goto("/en/app/animals");
  await page.locator("main ul li a").first().click();
  await page.getByRole("link", { name: "Add sighting" }).click();
  // 1×1 black JPEG scaled by the server? No: generate a real 640×480 black JPEG via a canvas in the page.
  const dataUrl = await page.evaluate(() => {
    const c = document.createElement("canvas");
    c.width = 640;
    c.height = 480;
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = "#030303";
    ctx.fillRect(0, 0, 640, 480);
    return c.toDataURL("image/jpeg", 0.9);
  });
  const buffer = Buffer.from(dataUrl.split(",")[1]!, "base64");
  await page.getByTestId("sighting-photo-file-input").setInputFiles({ name: "dark.jpg", mimeType: "image/jpeg", buffer });
  await expect(page.getByText("The photo is very dark.")).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Save sighting" }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText("Explain the reason");
  await page.getByLabel("Why use this photo anyway?").fill("Only photo taken at night");
  await page.getByRole("button", { name: "Save sighting" }).click();
  await page.waitForURL(/tab=sightings/);
});
