import path from "node:path";

import { expect, test } from "@playwright/test";

import { DEMO, ORGS, expectNoAxeViolations, signIn, switchOrg } from "./helpers";

/**
 * Phase 8 — campaign day planning on the demo campaign: a plan respects the coordinator's decisions, explains
 * what could not be planned, compares with the simple baseline, and creates team tasks only after approval and
 * publication. A revised input (fewer doses) produces a new version with honest infeasibility reasons.
 */
test.describe.configure({ mode: "serial" });
test.skip(({ isMobile }) => isMobile, "runs once on desktop");
test.setTimeout(180_000);

const SHOTS = path.resolve(import.meta.dirname, "../../docs/screenshots/phase8");

test("coordinator plans, approves and publishes a field day; revised inputs give a new version", async ({ page, browser }) => {
  await signIn(page, DEMO.coordinator.email);
  await switchOrg(page, ORGS.riverside);
  await page.getByRole("navigation", { name: "App navigation" }).first().getByRole("link", { name: "Campaign planning" }).click();
  await page.getByRole("link", { name: "Demo October vaccination round" }).click();
  await expect(page.getByRole("heading", { name: "Demo October vaccination round" })).toBeVisible();
  await expect(page.getByText(/Suggested 22: one street count on \d{4}-\d{2}-\d{2}/)).toBeVisible();
  await expect(page.getByText("they are not population sizes or vaccination coverage", { exact: false })).toBeVisible();
  await expectNoAxeViolations(page);

  // The coordinator leaves the market ward out; the plan must respect that
  await page.getByLabel("Demo Ward F — Market").selectOption({ label: "Leave out" });
  await page.getByRole("button", { name: "Make plan" }).click();
  await expect(page.getByText("Ready for review").first()).toBeVisible({ timeout: 60_000 });
  const main = page.getByRole("main");
  await expect(main.getByText("This is a proposal")).toBeVisible();
  await expect(main.getByText(/straight-line distance × 1\.3 at 15 km\/h/)).toBeVisible();
  await expect(main.getByText("Simple plan, for comparison")).toBeVisible();
  await expect(main.getByText(/Demo Ward F — Market\s*:\s*You left it out\./)).toBeVisible();
  await expectNoAxeViolations(page);
  await page.screenshot({ path: path.join(SHOTS, "planner-ready-1440.png"), fullPage: true });

  // Nothing reaches teams before approval + publication
  const tasksBefore = (await (await page.context().request.get("/api/v1/tasks?mine=false&state=assigned&limit=100")).json()).items.length;
  await page.getByRole("button", { name: "Approve plan" }).click();
  await page.getByRole("dialog").getByLabel("Note").fill("Checked with both team leads");
  await page.getByRole("dialog").getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("Approved by", { exact: false })).toBeVisible();
  const tasksAfterApprove = (await (await page.context().request.get("/api/v1/tasks?mine=false&state=assigned&limit=100")).json()).items.length;
  expect(tasksAfterApprove).toBe(tasksBefore);
  await page.getByRole("button", { name: "Publish as tasks" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText(/\d+ tasks? (was|were) created\./)).toBeVisible();

  // A member of team 1 sees the published stops among their tasks
  const vctx = await browser.newContext();
  const vol = await vctx.newPage();
  await signIn(vol, DEMO.volunteer.email);
  const mine = (await (await vol.context().request.get("/api/v1/tasks?mine=true&state=assigned&limit=100")).json()).items;
  expect(mine.some((t: { source_event_type: string | null }) => t.source_event_type === "campaign_plan")).toBe(true);
  await vctx.close();

  // Revised input: only team 2 with 10 doses → a new version that explains what cannot be done
  await page.getByLabel("Demo team 1").uncheck();
  await page.getByLabel("Doses").nth(1).fill("10");
  await page.getByRole("button", { name: "Make plan" }).click();
  await expect(page.getByRole("heading", { name: /Plan version \d+ for/ })).toBeVisible();
  await expect(page.getByText("Ready for review").first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("It needs more doses than any team carries.").first()).toBeVisible();
  await expect(page.getByText(/Demo Ward F — Market\s*:\s*You left it out\./)).toBeVisible(); // decision kept
  await expect(page.getByRole("heading", { name: "Plan versions" })).toBeVisible();
});
