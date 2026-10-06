import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { DEMO, expectNoAxeViolations, signIn } from "./helpers";

/** Staff can read the measured PawID evidence; the numbers on the page are the ones in results.json. */
const results = JSON.parse(fs.readFileSync(path.resolve(import.meta.dirname, "../../ml/eval/dogfacenet/results.json"), "utf8"));
const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

test("model evidence page shows the measured results and the caveat", async ({ page }) => {
  await signIn(page, DEMO.volunteer.email);
  await page.goto("/en/app/model-evidence");
  await expect(page.getByRole("heading", { level: 1, name: "Model evidence: photo matching" })).toBeVisible();
  await expect(page.getByText("Evaluated on DogFaceNet pet face photos; not yet validated on street dogs.")).toBeVisible();
  const main = page.getByRole("main");
  const head = results.test.pawid_dinov2s_head;
  for (const v of [head.top1.value, head.fpir.value, head.known_top1_correct_accepted.value, results.test.color_histogram.top1.value]) {
    await expect(main.getByText(pct(v), { exact: false }).first()).toBeVisible();
  }
  for (const img of await main.locator("img").all()) {
    expect(await img.evaluate((e) => (e as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  }
  await expectNoAxeViolations(page);
});
