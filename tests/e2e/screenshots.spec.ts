import { test } from "@playwright/test";

import { DEMO, signIn } from "./helpers";

/** Review evidence: full-page screenshots at the widths named in the design brief. Not a pixel-diff test. */
const WIDTHS = [360, 390, 768, 1440];

test.describe("visual review screenshots", () => {
  test.skip(({ isMobile }) => isMobile, "widths are set explicitly; run once");

  for (const width of WIDTHS) {
    test(`public pages at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      for (const [name, path] of [
        ["landing", "/en"],
        ["help", "/en/help"],
        ["help-ta", "/ta/help"],
        ["sign-in", "/en/sign-in"],
      ] as const) {
        await page.goto(path);
        await page.screenshot({ path: `../docs/screenshots/phase2/${name}-${width}.png`, fullPage: true });
      }
    });

    test(`app shell at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await signIn(page, DEMO.coordinator.email);
      await page.screenshot({ path: `../docs/screenshots/phase2/today-${width}.png`, fullPage: true });
    });
  }
});
