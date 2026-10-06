import { test } from "@playwright/test";

import { DEMO, signIn } from "./helpers";

/** Review evidence for Phase 4 screens (not pixel tests). Writes to docs/screenshots/phase4/. */
const OUT = "../docs/screenshots/phase4";

test.describe("phase 4 review screenshots", () => {
  test.skip(({ isMobile }) => isMobile, "widths set explicitly");
  for (const width of [360, 1440]) {
    test(`field and review screens at ${width}px`, async ({ page, browser }) => {
      await page.setViewportSize({ width, height: 900 });
      await signIn(page, DEMO.volunteer.email);
      await page.screenshot({ path: `${OUT}/today-volunteer-${width}.png`, fullPage: true });
      await page.goto("/en/app/animals");
      await page.screenshot({ path: `${OUT}/registry-${width}.png`, fullPage: true });
      await page.locator("main ul li a").first().click();
      await page.waitForURL(/\/app\/animals\/[0-9a-f-]+$/);
      await page.screenshot({ path: `${OUT}/profile-${width}.png`, fullPage: true });
      const profile = page.url();
      await page.goto(`${profile}?tab=sightings`);
      await page.screenshot({ path: `${OUT}/profile-sightings-${width}.png`, fullPage: true });
      await page.goto(`${profile}/vaccinations/new`);
      await page.screenshot({ path: `${OUT}/vaccination-form-${width}.png`, fullPage: true });
      await page.goto("/en/app/animals/new");
      await page.screenshot({ path: `${OUT}/new-animal-${width}.png`, fullPage: true });
      await page.goto("/en/app/tasks");
      await page.screenshot({ path: `${OUT}/tasks-${width}.png`, fullPage: true });

      const vetCtx = await browser.newContext({ viewport: { width, height: 900 } });
      const vet = await vetCtx.newPage();
      await signIn(vet, DEMO.vet.email);
      await vet.goto("/en/app/review");
      await vet.screenshot({ path: `${OUT}/review-${width}.png`, fullPage: true });
      await vet.goto("/en/app/map");
      await vet.waitForTimeout(2500);
      await vet.screenshot({ path: `${OUT}/map-${width}.png`, fullPage: true });
      await vetCtx.close();
    });
  }
});
