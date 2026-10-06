import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { DEMO, signIn } from "./helpers";

/** Review evidence: subject picker with real detector boxes (multi-dog photo, nothing preselected). */
test.skip(({ isMobile }) => isMobile, "desktop only");
test.setTimeout(150_000);

test("subject picker screenshots", async ({ page }) => {
  const root = path.resolve(import.meta.dirname, "../..");
  const manifest = path.join(root, "data/manifests/coco-val2017-dog-sample-v1.json");
  test.skip(!fs.existsSync(manifest), "COCO sample not available");
  const m = JSON.parse(fs.readFileSync(manifest, "utf8")) as { images: { file_name: string; split: string; dog_boxes_xywh: number[][] }[] };
  const multi = m.images.find((i) => i.split === "verification" && i.dog_boxes_xywh.length >= 2) ?? m.images[0]!;
  for (const width of [1440, 360]) {
    await page.setViewportSize({ width, height: 900 });
    await signIn(page, DEMO.volunteer.email);
    await page.goto("/en/app/animals");
    await page.locator("main ul li a").first().click();
    await page.getByRole("link", { name: "Add sighting" }).click();
    await page.getByTestId("sighting-photo-file-input").setInputFiles(path.join(root, "data/raw/coco/val2017_sample", multi.file_name));
    await expect(page.getByText(/Is this the dog|Several dogs may be in this photo|No dog was found/)).toBeVisible({ timeout: 90_000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `../docs/screenshots/phase5/subject-picker-${width}.png`, fullPage: true });
    await page.context().clearCookies();
  }
});
