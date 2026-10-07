import path from "node:path";

import { test, type Page } from "@playwright/test";

import { DEMO, ORGS, signIn, switchOrg } from "./helpers";

/** Phase 9 visual review of demonstrated screens (desktop project at 1440 px, mobile project at 360 px). */
const SHOTS = path.resolve(import.meta.dirname, "../../docs/screenshots/phase9/screens");

async function snap(page: Page, name: string, isMobile: boolean) {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.screenshot({ path: path.join(SHOTS, `${name}-${isMobile ? "360" : "1440"}.png`), fullPage: true });
}

test("volunteer screens", async ({ page, isMobile }) => {
  await signIn(page, DEMO.volunteer.email);
  for (const [name, url] of [["today", "/en/app"], ["registry", "/en/app/animals"], ["capture", "/en/app/capture"],
    ["tasks", "/en/app/tasks"], ["field", "/en/field"], ["more", "/en/app/more"], ["today-ta", "/ta/app"], ["tasks-ta", "/ta/app/tasks"]] as const) {
    await page.goto(url);
    await snap(page, `vol-${name}`, isMobile);
  }
});

test("coordinator and admin screens", async ({ page, isMobile }) => {
  await signIn(page, DEMO.coordinator.email);
  await switchOrg(page, ORGS.riverside);
  for (const [name, url] of [["campaigns", "/en/app/campaigns"], ["map", "/en/app/map"], ["imports", "/en/app/imports"]] as const) {
    await page.goto(url);
    await snap(page, `coord-${name}`, isMobile);
  }
  await page.goto("/en/app/campaigns");
  await page.getByRole("link", { name: "October vaccination round" }).click();
  await snap(page, "coord-planner", isMobile);
  await page.context().clearCookies();
  await signIn(page, DEMO.admin.email);
  await page.goto("/en/app/system");
  await snap(page, "admin-system", isMobile);
});

test("public and sign-in", async ({ page, isMobile }) => {
  for (const [name, url] of [["landing", "/en"], ["help", "/en/help"], ["sign-in", "/en/sign-in"]] as const) {
    await page.goto(url);
    await snap(page, `public-${name}`, isMobile);
  }
});
