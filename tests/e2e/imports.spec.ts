import { expect, test, type Browser, type Page } from "@playwright/test";

import { DEMO, ORGS, expectNoAxeViolations, signIn, switchOrg } from "./helpers";

/**
 * Phase 6 — partner CSV import: a coordinator uploads a file, reviews the row-by-row dry-run report, applies only
 * the valid rows, and rolls the import back (records archived, not deleted). A volunteer has no import access.
 * The CSV is synthetic and unique per run (the API refuses a byte-identical file twice).
 */
test.describe.configure({ mode: "serial" });
test.skip(({ isMobile }) => isMobile, "journey runs once on desktop");

const run = Date.now().toString(36).toUpperCase();
const CSV = [
  "source_row_id,nickname,species,sex,sterilisation_status,age_band,ownership_category,area_code,last_seen_date,coat_description",
  `E2E-${run}-1,Imported ${run},dog,F,yes,adult,street,W-A,2026-09-01,Tan with white socks`,
  `E2E-${run}-2,Second ${run},canine,M,intact,pup,stray,NOPE,2026-09-02,Brown`,
  `E2E-${run}-3,,dog,?,maybe,old,community,W-A,2099-01-01,White`,
].join("\n");

async function as(browser: Browser, email: string): Promise<Page> {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await signIn(page, email);
  return page;
}

test("volunteer has no import access", async ({ browser }) => {
  const page = await as(browser, DEMO.volunteer.email);
  const appNav = page.getByRole("navigation", { name: "App navigation" }).first();
  await expect(appNav.getByRole("link", { name: "Data imports" })).toHaveCount(0);
  await page.goto("/en/app/imports");
  await expect(page.getByRole("main").getByText("Data imports")).toHaveCount(0);
  await expect(page.getByRole("main").getByLabel("CSV file")).toHaveCount(0);
});

test("coordinator checks, applies and rolls back a partner CSV", async ({ browser }) => {
  const page = await as(browser, DEMO.coordinator.email);
  await switchOrg(page, ORGS.riverside); // Meena coordinates Riverside; she is only a volunteer at Hillview
  await page.getByRole("navigation", { name: "App navigation" }).first().getByRole("link", { name: "Data imports" }).click();
  await page.waitForURL(/\/app\/imports$/);
  await expectNoAxeViolations(page);
  await page.getByLabel("Where is this file from?").fill(`E2E partner export ${run}`);
  await page.getByLabel("CSV file").setInputFiles({ name: "partner.csv", mimeType: "text/csv", buffer: Buffer.from(CSV) });
  await page.getByRole("button", { name: "Check file" }).click();
  await page.waitForURL(/\/app\/imports\?id=/);
  const main = page.getByRole("main");
  await expect(main.getByText("Nothing has been created yet")).toBeVisible();
  const row = (n: number) => main.getByRole("row").filter({ has: page.getByRole("cell", { name: String(n), exact: true }) });
  await expect(row(2).getByText("Valid", { exact: true })).toBeVisible();
  await expect(row(3).getByText("Warning", { exact: true })).toBeVisible();
  await expect(row(3).getByText(/Unknown area code/)).toBeVisible();
  await expect(row(4).getByText("Rejected", { exact: true })).toBeVisible();
  await expect(row(4).getByText(/future/i)).toBeVisible();
  await expectNoAxeViolations(page);

  // Nothing exists until applied
  const api = page.context().request;
  const before = await (await api.get(`/api/v1/animals?q=${encodeURIComponent(`Imported ${run}`)}`)).json();
  expect(before.total_matching).toBe(0);

  await page.getByRole("button", { name: "Apply 1 row" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Create records from 1 row?")).toBeVisible();
  await dialog.getByRole("button", { name: "Confirm" }).click();
  await expect(main.getByText("Applied", { exact: true }).first()).toBeVisible({ timeout: 30_000 });
  const after = await (await api.get(`/api/v1/animals?q=${encodeURIComponent(`Imported ${run}`)}`)).json();
  expect(after.total_matching).toBe(1);
  expect(after.items[0].profile_state).toBe("provisional");
  const warned = await (await api.get(`/api/v1/animals?q=${encodeURIComponent(`Second ${run}`)}`)).json();
  expect(warned.total_matching).toBe(0); // warning rows were not included

  await page.getByRole("button", { name: "Roll back this import" }).click();
  await dialog.getByLabel("Reason").fill("E2E check of the rollback path");
  await dialog.getByRole("button", { name: "Confirm" }).click();
  await expect(main.getByText("Rolled back (records archived)").first()).toBeVisible({ timeout: 30_000 });
  const gone = await (await api.get(`/api/v1/animals?q=${encodeURIComponent(`Imported ${run}`)}`)).json();
  expect(gone.total_matching).toBe(0);
  await expect(main.getByRole("link", { name: new RegExp(`E2E partner export ${run}`) })).toBeVisible();
});
