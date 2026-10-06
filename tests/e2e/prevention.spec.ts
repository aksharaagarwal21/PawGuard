import path from "node:path";

import { expect, test, type Browser, type Page } from "@playwright/test";

import { DEMO, ORGS, expectNoAxeViolations, signIn, switchOrg } from "./helpers";

/**
 * Phase 4 — the complete manual Prevention journey with no AI service involved:
 * volunteer registers an animal and submits vaccination evidence → a different, authorised reviewer requests a
 * correction → the volunteer amends → the reviewer verifies → profile and programme views update → another
 * tenant cannot see it → a duplicate merge is approved and reversed by a second person.
 * Runs once (desktop project) against the demo tenant.
 */
test.describe.configure({ mode: "serial" });
test.skip(({ isMobile }) => isMobile, "journey runs once on desktop; mobile layout is covered by screenshots");

const FIXTURES = path.resolve(import.meta.dirname, "../fixtures");
const FORBIDDEN = ["safe dog", "rabies-free", "unvaccinated", "% match", "ai verified", "is vaccinated"];
const coat = `E2E coat ${Date.now()}`;
let animalUrl = "";
let reference = "";
let firstEventUrl = "";
let amendedEventUrl = "";

async function as(browser: Browser, email: string): Promise<Page> {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await signIn(page, email);
  return page;
}

async function expectNoForbiddenWording(page: Page) {
  // The approved explanation negates the label ("does not mean the animal is unvaccinated"); remove it so any
  // remaining occurrence would be a derived label.
  const text = (await page.locator("main").innerText()).toLowerCase().replaceAll("does not mean the animal is unvaccinated", "");
  for (const f of FORBIDDEN) expect(text, `"${f}" must never appear`).not.toContain(f);
}

test("volunteer registers a provisional animal with a photo", async ({ browser }) => {
  const page = await as(browser, DEMO.volunteer.email);
  const appNav = page.getByRole("navigation", { name: "App navigation" }).first();
  await expect(appNav.getByRole("link", { name: "Review", exact: true })).toHaveCount(0); // no review authority
  await page.getByRole("link", { name: "Register an animal" }).first().click();
  await expect(page.getByRole("heading", { name: /Step 1/ })).toBeFocused();
  await expectNoAxeViolations(page);
  await page.getByLabel("Coat description").fill(coat);
  await page.getByLabel("Identifying marks").fill("Left ear notched; white tip on tail");
  await page.getByText("Female", { exact: true }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Area").selectOption({ label: "Demo Ward A — North" });
  await page.getByTestId("new-animal-photo-file-input").setInputFiles(path.join(FIXTURES, "synthetic-animal.jpg"));
  await expect(page.getByText(/^(Ready|Checking the file…|Saved\. It will be checked shortly)/)).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText(coat)).toBeVisible();
  await page.getByRole("button", { name: "Save provisional profile" }).click();
  await page.waitForURL(/\/app\/animals\/[0-9a-f-]+\?created=1/);
  await expect(page.getByText(/Provisional profile PG-[0-9A-Z]{4}-[0-9A-Z]{4} created\./)).toBeVisible();
  await expect(page.getByText("No verified vaccination record").first()).toBeVisible();
  await expect(page.getByText("does not mean the animal is unvaccinated", { exact: false })).toBeVisible();
  animalUrl = page.url().split("?")[0]!;
  reference = (await page.getByRole("heading", { level: 1 }).innerText()).match(/PG-[0-9A-Z]{4}-[0-9A-Z]{4}/)![0];
  await expectNoAxeViolations(page);
  await expectNoForbiddenWording(page);
  await page.context().close();
});

test("volunteer submits vaccination evidence — shown as submitted, not verified", async ({ browser }) => {
  const page = await as(browser, DEMO.volunteer.email);
  await page.goto(animalUrl);
  await page.getByRole("link", { name: "Record vaccination evidence" }).click();
  await expectNoAxeViolations(page);
  const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
  await page.getByLabel("Date", { exact: true }).fill(yesterday);
  await page.getByLabel("Vaccine product").selectOption({ label: "DEMO Rabies Vaccine A (fictional)" });
  await page.getByLabel("Lot / batch number").selectOption({ label: "DEMO-A-001" });
  await page.getByLabel("Given by (name)").fill("Dr Fictional (demo)");
  await page.getByTestId("vacc-evidence-file-input").setInputFiles(path.join(FIXTURES, "synthetic-certificate.jpg"));
  await expect(page.getByText(/^(Ready|Checking the file…|Saved\. It will be checked shortly)/)).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Submit for review" }).click();
  await page.waitForURL(/\/app\/vaccinations\/[0-9a-f-]+\?submitted=1/);
  firstEventUrl = page.url().split("?")[0]!;
  await expect(page.getByText("Submitted for review").first()).toBeVisible();
  await expect(page.getByText("Verified administration record")).toHaveCount(0);
  await expectNoAxeViolations(page);
  await page.context().close();
});

test("a different, authorised reviewer requests a correction", async ({ browser }) => {
  const page = await as(browser, DEMO.vet.email);
  const eventId = firstEventUrl.split("/").pop()!;
  await page.goto(`/en/app/review?id=${eventId}`);
  await expect(page.getByRole("heading", { name: reference })).toBeVisible();
  await expectNoAxeViolations(page);
  await page.getByRole("button", { name: "Request correction" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Request correction" }).click();
  await expect(page.getByRole("dialog").getByText("Explain the reason (required).")).toBeVisible();
  await page.getByLabel("Reason (shown to the submitter)").fill("Please confirm the lot number against the vial label.");
  await page.getByRole("dialog").getByRole("button", { name: "Request correction" }).click();
  await expect(page.getByText("Correction requested. The submitter has a task to fix it.")).toBeVisible();
  await page.context().close();
});

test("volunteer sees the correction on Today and amends the record", async ({ browser }) => {
  const page = await as(browser, DEMO.volunteer.email);
  await expect(page.getByRole("heading", { name: "Corrections requested" })).toBeVisible();
  await page.getByRole("link", { name: reference }).first().click();
  await expect(page.getByText("Please confirm the lot number against the vial label.").first()).toBeVisible();
  await page.getByRole("link", { name: "Correct this record" }).click();
  await page.getByLabel("Lot / batch number").selectOption({ label: "Type the lot number as written" });
  await page.getByLabel("Lot number", { exact: true }).fill("DEMO-A-001/B");
  await page.getByRole("button", { name: "Submit for review" }).click();
  await page.waitForURL(/\/app\/vaccinations\/[0-9a-f-]+\?submitted=1/);
  amendedEventUrl = page.url().split("?")[0]!;
  expect(amendedEventUrl).not.toBe(firstEventUrl);
  await expect(page.getByText("Corrects an earlier record")).toBeVisible();
  await page.goto(firstEventUrl);
  await expect(page.getByText("Replaced by a later correction").first()).toBeVisible(); // original kept
  await page.context().close();
});

test("reviewer verifies; profile and programme views update with honest wording", async ({ browser }) => {
  const page = await as(browser, DEMO.vet.email);
  await page.goto(`/en/app/review?id=${amendedEventUrl.split("/").pop()}`);
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("dialog").getByText("does not certify that the animal cannot carry", { exact: false })).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Verify" }).click();
  await expect(page.getByText("Record verified.")).toBeVisible();
  await page.goto(animalUrl);
  await expect(page.getByText(/Last verified vaccination record: /).first()).toBeVisible();
  await expect(page.getByText("It does not mean the animal cannot carry or transmit disease.")).toBeVisible();
  await expectNoForbiddenWording(page);
  await page.goto(`${animalUrl}?tab=vaccinations`);
  await expect(page.getByText("Verified administration record")).toBeVisible();
  await expect(page.getByText("Replaced by a later correction")).toBeVisible();
  await page.goto("/en/app/map");
  await expect(page.getByText("Registry measures, not population coverage", { exact: false })).toBeVisible();
  await expect(page.getByRole("table")).toBeVisible();
  await page.context().close();
});

test("another organisation cannot see the record", async ({ browser }) => {
  const page = await as(browser, DEMO.hillVolunteer.email);
  const res = await page.goto(animalUrl);
  expect(res?.status()).toBe(404);
  await page.goto(`/en/app/animals?q=${encodeURIComponent(reference)}`);
  await expect(page.getByText("No animals match")).toBeVisible();
  await page.context().close();
});

test("duplicate merge: proposed by one person, approved and reversed by another", async ({ browser }) => {
  // Volunteer proposes: the E2E animal looks like an existing registered dog.
  const vol = await as(browser, DEMO.volunteer.email);
  await vol.goto("/en/app/animals?q=brindle");
  const targetRef = (await vol.locator("main ul li .font-mono").first().innerText()).trim();
  await vol.goto(animalUrl);
  await vol.getByRole("link", { name: "This may be a duplicate" }).click();
  await vol.getByLabel("Reference of the record to keep").fill(targetRef);
  await vol.getByRole("button", { name: "Compare" }).click();
  await expect(vol.getByRole("heading", { name: "Record to keep" })).toBeVisible();
  await expect(vol.getByText("Vaccination records", { exact: true })).toBeVisible();
  await vol.getByLabel("Why are these the same animal?").fill("Same coat and ear notch seen at the same corner.");
  await vol.getByRole("button", { name: "Propose merge" }).click();
  await vol.waitForURL(/[/]app[/]merges[/][0-9a-f-]+[?]proposed=1/);
  const mergeUrl = vol.url().split("?")[0]!;
  await expect(vol.getByText("Proposed — waiting for a second person")).toBeVisible();
  await expect(vol.getByRole("button", { name: "Approve and merge" })).toHaveCount(0); // proposer cannot approve
  await vol.context().close();

  // Coordinator (second person, animal.merge) approves, then reverses.
  const page = await as(browser, DEMO.coordinator.email);
  await switchOrg(page, ORGS.riverside);
  await page.goto(mergeUrl);
  await page.getByLabel("Reason for your decision").fill("Coat, marks and area match; same dog.");
  await page.getByRole("button", { name: "Approve and merge" }).click();
  await expect(page.getByText("Merged", { exact: true }).first()).toBeVisible();
  await page.goto(animalUrl);
  await expect(page.getByText(`This record was merged into ${targetRef}`, { exact: false })).toBeVisible();
  await page.goto(mergeUrl);
  await page.getByLabel("Reason for your decision").fill("Checked again: different collars, reversing.");
  await page.getByRole("button", { name: "Reverse merge" }).click();
  await expect(page.getByText("Reversed", { exact: true }).first()).toBeVisible();
  await page.goto(animalUrl);
  await expect(page.getByText(/Last verified vaccination record: /).first()).toBeVisible(); // history restored
  await page.context().close();
});

test("the manual path is complete with no AI; photo matching is never presented as validated", async ({ browser }) => {
  const page = await as(browser, DEMO.volunteer.email);
  const status = await (await page.context().request.get("/api/v1/identity/status")).json();
  expect(["unavailable", "research_preview"]).toContain(status.mode); // no validated identity model exists
  await page.goto("/en/app/capture");
  if (status.mode === "unavailable") await expect(page.getByText("Photo comparison isn't available")).toBeVisible();
  else await expect(page.getByText("Research preview — not validated")).toBeVisible();
  await expect(page.getByRole("link", { name: "Find the animal in the registry" })).toBeVisible();
  await page.goto("/en/app/animals?q=brindle");
  await expect(page.getByText(/records? in this registry/)).toBeVisible();
  await expectNoAxeViolations(page);
  await expectNoForbiddenWording(page);
  await page.goto("/en/app/tasks");
  await expectNoAxeViolations(page);
  await page.context().close();
});
