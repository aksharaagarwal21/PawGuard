import fs from "node:fs";
import path from "node:path";

import { expect, test, type Browser, type Page } from "@playwright/test";

import { DEMO, ORGS, expectNoAxeViolations, signIn, switchOrg } from "./helpers";

/**
 * Phase 9 — the Prevention release walkthrough, as shown in the demonstration, on desktop and on a 360 px phone:
 * volunteer signs in → finds an existing animal, then registers a new one → records a sighting → submits
 * vaccination evidence → (a forged "verify" request from the volunteer is refused) → works the assigned task →
 * an authorised veterinary reviewer verifies → history and task update and persist after reload → another
 * organisation cannot reach any of it.
 */
test.describe.configure({ mode: "serial" });
test.setTimeout(240_000);

const ROOT = path.resolve(import.meta.dirname, "../..");
const FIXTURES = path.join(ROOT, "tests/fixtures");
const SHOTS = path.join(ROOT, "docs/screenshots/phase9");
fs.mkdirSync(SHOTS, { recursive: true });
const FORBIDDEN = ["safe dog", "rabies-free", "% match", "ai verified", "is vaccinated"];

async function gatewayFetch(page: Page, method: string, url: string, body?: unknown): Promise<{ status: number; json: any }> {
  return page.evaluate(
    async ([m, u, b]) => {
      const token = document.cookie.split("; ").find((c) => c.startsWith("pg_csrf="))?.slice(8) ?? "";
      const r = await fetch(u as string, {
        method: m as string,
        headers: { "content-type": "application/json", "x-pawguard-csrf": decodeURIComponent(token) },
        body: b === undefined ? undefined : JSON.stringify(b),
      });
      return { status: r.status, json: await r.json().catch(() => null) };
    },
    [method, url, body] as const,
  );
}

async function contextFor(browser: Browser, email: string, mobile: boolean): Promise<Page> {
  const ctx = await browser.newContext(mobile ? { viewport: { width: 360, height: 780 }, isMobile: true, hasTouch: true } : { viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await signIn(page, email);
  return page;
}

async function shot(page: Page, name: string, mobile: boolean) {
  await page.screenshot({ path: path.join(SHOTS, `${name}-${mobile ? "360" : "1440"}.png`), fullPage: true });
}

async function noForbiddenWording(page: Page) {
  const text = (await page.locator("main").innerText()).toLowerCase();
  for (const f of FORBIDDEN) expect(text, `"${f}" must never appear`).not.toContain(f);
}

test("Prevention walkthrough: register → sighting → evidence → task → verification → persistence → isolation", async ({ browser, isMobile }) => {
  const stamp = `${isMobile ? "M" : "D"}${Date.now().toString(36)}`;
  const coat = `Walkthrough coat ${stamp}`;

  // Coordinator gives the volunteer a task for today (as a programme would)
  const coord = await contextFor(browser, DEMO.coordinator.email, false);
  await switchOrg(coord, ORGS.riverside);
  const vol = await contextFor(browser, DEMO.volunteer.email, isMobile);
  const me = await (await vol.context().request.get("/api/v1/me/organisation")).json();
  const made = await gatewayFetch(coord, "POST", "/api/v1/tasks", {
    task_type: "vaccination_round", title: `Walkthrough round ${stamp}`, assignee_membership_id: me.membership_id,
    instructions: "Register new dogs, record sightings and evidence.",
  });
  expect(made.status).toBe(201);

  // 1. Volunteer starts the task
  await vol.goto("/en/app/tasks");
  const task = vol.getByRole("listitem").filter({ hasText: `Walkthrough round ${stamp}` });
  await task.getByRole("button", { name: "Start" }).click();
  await expect(task.getByText("In progress")).toBeVisible();
  await shot(vol, "01-tasks", isMobile);

  // 2. Finds existing animals first (search), then registers a new one with a photo
  await vol.goto("/en/app/animals?q=brindle");
  await expect(vol.getByText(/records? in this registry/)).toBeVisible();
  await vol.goto("/en/app/animals/new");
  await vol.getByLabel("Coat description").fill(coat);
  await vol.getByLabel("Identifying marks").fill("Notched left ear");
  await vol.getByText("Female", { exact: true }).click();
  await vol.getByRole("button", { name: "Continue" }).click();
  await vol.getByLabel("Area").selectOption({ label: "Demo Ward A — North" });
  await vol.getByTestId("new-animal-photo-file-input").setInputFiles(path.join(FIXTURES, "synthetic-animal.jpg"));
  await expect(vol.getByText(/^(Ready|Checking the file…|Saved\. It will be checked shortly)/)).toBeVisible({ timeout: 30_000 });
  await vol.getByRole("button", { name: "Continue" }).click();
  await vol.getByRole("button", { name: "Save provisional profile" }).click();
  await vol.waitForURL(/\/app\/animals\/[0-9a-f-]{36}\?created=1/);
  const animalUrl = vol.url().split("?")[0]!;
  const animalId = animalUrl.split("/").pop()!;
  const reference = (await vol.getByRole("heading", { level: 1 }).innerText()).match(/PG-[0-9A-Z]{4}-[0-9A-Z]{4}/)![0];
  await expect(vol.getByText("No verified vaccination record").first()).toBeVisible();
  await noForbiddenWording(vol);
  await expectNoAxeViolations(vol);
  await shot(vol, "02-profile-new", isMobile);

  // 3. Records a sighting
  await vol.goto(`/en/app/capture?animal=${animalId}`);
  await vol.getByLabel("Notes").fill("Seen near the bus stand with two others");
  await vol.getByRole("button", { name: "Save sighting" }).click();
  await vol.waitForURL(/tab=sightings/);
  await expect(vol.getByText("Seen near the bus stand with two others")).toBeVisible();
  await expect(vol.getByText("Last seen: today").first()).toBeVisible(); // calendar day in the org's timezone

  // 4. Submits vaccination evidence
  await vol.goto(animalUrl);
  await vol.getByRole("link", { name: "Record vaccination evidence" }).click();
  const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
  await vol.getByLabel("Date", { exact: true }).fill(yesterday);
  await vol.getByLabel("Vaccine product").selectOption({ label: "DEMO Rabies Vaccine A (fictional)" });
  await vol.getByLabel("Lot / batch number").selectOption({ label: "DEMO-A-001" });
  await vol.getByLabel("Given by (name)").fill("Dr Fictional (demo)");
  await vol.getByTestId("vacc-evidence-file-input").setInputFiles(path.join(FIXTURES, "synthetic-certificate.jpg"));
  await expect(vol.getByText(/^(Ready|Checking the file…|Saved\. It will be checked shortly)/)).toBeVisible({ timeout: 30_000 });
  await expectNoAxeViolations(vol);
  await vol.getByRole("button", { name: "Submit for review" }).click();
  await vol.waitForURL(/\/app\/vaccinations\/[0-9a-f-]{36}\?submitted=1/);
  const eventId = vol.url().split("?")[0]!.split("/").pop()!;
  await expect(vol.getByText("Submitted for review").first()).toBeVisible();
  await shot(vol, "03-evidence-submitted", isMobile);

  // 5. The volunteer cannot verify their own submission, even with a hand-made request
  const event = await (await vol.context().request.get(`/api/v1/vaccination-events/${eventId}`)).json();
  const forged = await gatewayFetch(vol, "POST", `/api/v1/vaccination-events/${eventId}/reviews`, { outcome: "verified", row_version: event.row_version });
  expect(forged.status).toBe(403);
  expect(forged.json.error.code).toBe("missing_capability");
  expect((await (await vol.context().request.get(`/api/v1/vaccination-events/${eventId}`)).json()).state).toBe("submitted");

  // 6. Completes the task
  await vol.goto("/en/app/tasks");
  await task.getByRole("button", { name: "Mark complete" }).click();
  await vol.getByRole("dialog").getByLabel("What was done (optional)").fill(`Registered ${reference}, evidence submitted`);
  await vol.getByRole("dialog").getByRole("button", { name: "Confirm" }).click();
  await expect(vol.getByText("Task updated.").first()).toBeVisible();

  // 7. Another organisation cannot reach the animal, the record or the task
  const hill = await contextFor(browser, DEMO.hillVolunteer.email, false);
  expect((await hill.context().request.get(`/api/v1/animals/${animalId}`)).status()).toBe(404);
  expect((await hill.context().request.get(`/api/v1/vaccination-events/${eventId}`)).status()).toBe(404);
  expect((await hill.context().request.get(`/api/v1/tasks/${made.json.id}`)).status()).toBe(404);
  expect((await hill.goto(animalUrl))?.status()).toBe(404);
  await hill.context().close();

  // 8. An approved veterinary reviewer (a different person) verifies
  const vet = await contextFor(browser, DEMO.vet.email, isMobile);
  await vet.goto(`/en/app/review?id=${eventId}`);
  await expect(vet.getByRole("heading", { name: reference })).toBeVisible();
  await expectNoAxeViolations(vet);
  await shot(vet, "04-review", isMobile);
  await vet.getByRole("button", { name: "Verify" }).click();
  await expect(vet.getByRole("dialog").getByText("does not certify that the animal cannot carry", { exact: false })).toBeVisible();
  await vet.getByRole("dialog").getByRole("button", { name: "Verify" }).click();
  await expect(vet.getByText("Record verified.")).toBeVisible();
  await vet.context().close();

  // 9. History and task reflect it — and persist after reload
  await vol.goto(animalUrl);
  await vol.reload();
  await expect(vol.getByText(/Last verified vaccination record: /).first()).toBeVisible();
  await expect(vol.getByText("It does not mean the animal cannot carry or transmit disease.")).toBeVisible();
  await noForbiddenWording(vol);
  await shot(vol, "05-profile-verified", isMobile);
  await vol.goto(`${animalUrl}?tab=vaccinations`);
  await vol.reload();
  await expect(vol.getByText("Verified administration record")).toBeVisible();
  await vol.goto(`${animalUrl}?tab=sightings`);
  await expect(vol.getByText("Seen near the bus stand with two others")).toBeVisible();
  const done = await (await vol.context().request.get(`/api/v1/tasks/${made.json.id}`)).json();
  expect(done.state).toBe("completed");
  expect(done.outcome_note).toContain(reference);
  await vol.context().close();
  await coord.context().close();
});
