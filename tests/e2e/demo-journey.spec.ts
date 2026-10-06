import fs from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

/**
 * The hackathon demonstration, exactly as presented, recorded as a video (one browser window, one-click demo
 * sign-in so no password is typed): volunteer looks up the prepared photo → reviews possible matches → confirms
 * the animal → submits vaccination evidence → vet verifies → profile updates and persists after refresh.
 * Needs `bash scripts/demo_up.sh --reset` (or demo-reset + demo_prepare) beforehand. Desktop only.
 *   cd tests && pnpm exec playwright test e2e/demo-journey.spec.ts --project=desktop
 * Video: backups/demo-recording/ (ignored by Git).
 */
test.skip(({ isMobile }) => isMobile, "desktop demonstration");
test.setTimeout(300_000);

const ROOT = path.resolve(import.meta.dirname, "../..");
const FIXTURES = path.join(ROOT, "tests/fixtures");
const VIDEO_DIR = path.join(ROOT, "backups/demo-recording");
const PAUSE = 900; // readable pacing for the recording

function preparedPhoto(): string | null {
  const m = JSON.parse(fs.readFileSync(path.join(ROOT, "data/manifests/coco-val2017-dog-sample-v1.json"), "utf8")) as {
    images: { file_name: string; split: string; dog_boxes_xywh: number[][] }[];
  };
  const e = m.images.find((i) => i.split === "verification" && i.dog_boxes_xywh.length === 1);
  const p = e ? path.join(ROOT, "data/raw/coco/val2017_sample", e.file_name) : null;
  return p && fs.existsSync(p) ? p : null;
}

async function demoSignIn(page: Page, name: string) {
  await page.goto("/en/sign-in");
  await page.getByRole("button", { name: new RegExp(`^Sign in as ${name}`) }).click();
  await page.waitForURL(/\/en\/app$/);
  await page.waitForTimeout(PAUSE);
}

async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out" }).first().click();
  await page.waitForURL(/signed_out=1/);
}

test("hackathon demo journey (recorded)", async ({ browser }) => {
  const photo = preparedPhoto();
  test.skip(!photo, "prepared COCO photo not found — run scripts/demo_prepare.py");
  fs.mkdirSync(VIDEO_DIR, { recursive: true });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, recordVideo: { dir: VIDEO_DIR, size: { width: 1280, height: 800 } } });
  const page = await ctx.newPage();
  const log: string[] = [];

  // 1. Volunteer signs in (one-click demo account)
  await demoSignIn(page, "Priya");
  log.push("Signed in as Priya (volunteer)");

  // 2. Find an animal from the prepared photo
  await page.getByRole("navigation", { name: "App navigation" }).first().getByRole("link", { name: "Add photo" }).click();
  await expect(page.getByRole("heading", { name: "Find an animal from a photo" })).toBeVisible();
  await expect(page.getByText("Research preview — not validated")).toBeVisible();
  await page.waitForTimeout(PAUSE);
  await page.getByTestId("lookup-photo-file-input").setInputFiles(photo!);
  await expect(page.getByText("Dog 1", { exact: true })).toBeVisible({ timeout: 90_000 });
  await page.waitForTimeout(PAUSE);
  await page.getByText("Dog 1", { exact: true }).click();
  const reason = page.getByLabel("Why use this photo anyway?");
  if (await reason.count()) await reason.fill("Clearest photo taken today");
  await page.getByRole("button", { name: "Look for possible matches" }).click();
  await expect(page.getByRole("heading", { name: "Possible matches" })).toBeVisible({ timeout: 90_000 });
  await page.waitForTimeout(PAUSE * 2);
  const main = page.getByRole("main");
  const candidates = main.getByRole("listitem").filter({ has: page.getByRole("button", { name: "This is the same animal" }) });
  let reference: string;
  if ((await candidates.count()) > 0) {
    // 3. Review and confirm the possible match
    const first = candidates.first();
    reference = (await first.innerText()).match(/PG-[0-9A-Z]{4}-[0-9A-Z]{4}/)![0];
    log.push(`Possible match 1: ${reference} (no percentage shown)`);
    expect(await main.innerText()).not.toMatch(/\d+\s?%/);
    await first.getByRole("button", { name: "This is the same animal" }).scrollIntoViewIfNeeded();
    await page.waitForTimeout(PAUSE);
    await first.getByRole("button", { name: "This is the same animal" }).click();
    await expect(page.getByRole("dialog").getByText(`Record this photo as a sighting of ${reference}?`)).toBeVisible();
    await page.waitForTimeout(PAUSE);
    await page.getByRole("dialog").getByRole("button", { name: "Yes, same animal" }).click();
    await page.waitForURL(/\/app\/animals\/[0-9a-f-]{36}\?tab=sightings/);
    log.push("Confirmed: sighting recorded on the animal's profile");
  } else {
    // No candidate: the honest result, then the manual path
    log.push(`No candidate shown: ${(await main.innerText()).match(/No similar animals found|Results may be incomplete/)?.[0]}`);
    await page.getByRole("link", { name: "Search the registry instead" }).click();
    await page.locator("main ul li a").first().click();
    await page.waitForURL(/\/app\/animals\/[0-9a-f-]{36}/);
    reference = (await page.getByRole("heading", { level: 1 }).innerText()).match(/PG-[0-9A-Z]{4}-[0-9A-Z]{4}/)![0];
  }
  const animalUrl = page.url().split("?")[0]!;
  await page.waitForTimeout(PAUSE);

  // 4. Submit vaccination evidence
  await page.goto(animalUrl);
  await page.getByRole("link", { name: "Record vaccination evidence" }).click();
  const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
  await page.getByLabel("Date", { exact: true }).fill(yesterday);
  await page.getByLabel("Vaccine product").selectOption({ label: "DEMO Rabies Vaccine A (fictional)" });
  await page.getByLabel("Lot / batch number").selectOption({ label: "DEMO-A-001" });
  await page.getByLabel("Given by (name)").fill("Dr Fictional (demo)");
  await page.getByTestId("vacc-evidence-file-input").setInputFiles(path.join(FIXTURES, "synthetic-certificate.jpg"));
  await expect(page.getByText(/^(Ready|Checking the file…|Saved\. It will be checked shortly)/)).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(PAUSE);
  await page.getByRole("button", { name: "Submit for review" }).click();
  await page.waitForURL(/\/app\/vaccinations\/[0-9a-f-]{36}\?submitted=1/);
  await expect(page.getByText("Submitted for review").first()).toBeVisible();
  log.push("Evidence submitted: 'Submitted for review'");
  await page.waitForTimeout(PAUSE * 2);
  await signOut(page);

  // 5. Veterinary reviewer verifies
  await demoSignIn(page, "Dr Arun");
  await page.getByRole("navigation", { name: "App navigation" }).first().getByRole("link", { name: "Review" }).click();
  await page.getByRole("link", { name: new RegExp(reference) }).first().click();
  await expect(page.getByRole("heading", { name: reference })).toBeVisible();
  await page.waitForTimeout(PAUSE * 2);
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("dialog").getByText("does not certify that the animal cannot carry", { exact: false })).toBeVisible();
  await page.waitForTimeout(PAUSE * 2);
  await page.getByRole("dialog").getByRole("button", { name: "Verify" }).click();
  await expect(page.getByText("Record verified.")).toBeVisible();
  log.push("Dr Arun verified the record");
  await page.waitForTimeout(PAUSE);
  await signOut(page);

  // 6. The profile updates and persists after refresh
  await demoSignIn(page, "Priya");
  await page.goto(animalUrl);
  await expect(page.getByText(/Last verified vaccination record: /).first()).toBeVisible();
  await page.waitForTimeout(PAUSE);
  await page.reload();
  await expect(page.getByText(/Last verified vaccination record: /).first()).toBeVisible();
  await expect(page.getByText("It does not mean the animal cannot carry or transmit disease.")).toBeVisible();
  await page.waitForTimeout(PAUSE * 2);
  log.push("After refresh: 'Last verified vaccination record' + disclaimer shown");
  await ctx.close();
  const video = await page.video()?.path();
  console.log(["DEMO JOURNEY", ...log, `video: ${video}`].join("\n  "));
});
