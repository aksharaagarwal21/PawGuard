import path from "node:path";

import { expect, test, type Browser, type Page } from "@playwright/test";

import { DEMO, ORGS, expectNoAxeViolations, signIn, switchOrg } from "./helpers";

/**
 * Phase 8 — offline field work on a trusted device: opt in, lose the connection, keep working from the field kit,
 * reconnect and replay; a re-sent operation is a duplicate (applied once); a change the server made meanwhile is
 * a conflict the person resolves; signing out with unsent changes warns and then wipes the device.
 * (Replay with revoked permissions is covered in services/api/tests/test_sync.py.)
 */
test.describe.configure({ mode: "serial" });
test.skip(({ isMobile }) => isMobile, "runs once on desktop");
test.setTimeout(180_000);

/** Same-origin mutation from inside the page (the gateway requires Origin + the CSRF header). */
async function apiPost(page: Page, path: string, body: unknown): Promise<{ status: number; json: any }> {
  return page.evaluate(
    async ([p, b]) => {
      const token = document.cookie.split("; ").find((c) => c.startsWith("pg_csrf="))?.slice(8) ?? "";
      const r = await fetch(p as string, {
        method: "POST",
        headers: { "content-type": "application/json", "x-pawguard-csrf": decodeURIComponent(token) },
        body: JSON.stringify(b),
      });
      return { status: r.status, json: await r.json().catch(() => null) };
    },
    [path, body] as const,
  );
}

async function as(browser: Browser, email: string): Promise<Page> {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  await signIn(page, email);
  return page;
}

test("offline field work: opt in, work offline, replay, duplicate, conflict, sign-out wipe", async ({ browser }) => {
  const vol = await as(browser, DEMO.volunteer.email);
  const coord = await as(browser, DEMO.coordinator.email);
  await switchOrg(coord, ORGS.riverside);
  const meRes = await vol.context().request.get("/api/v1/me/organisation");
  const me = await meRes.json();
  expect(me.membership_id, `${meRes.status()} ${JSON.stringify(me)}`).toBeTruthy();
  const animal = (await (await vol.context().request.get("/api/v1/animals?limit=1")).json()).items[0];
  const stamp = Date.now().toString(36);
  const made = await apiPost(coord, "/api/v1/tasks", {
    task_type: "animal_followup", title: `Offline check ${stamp}`, animal_id: animal.id,
    assignee_membership_id: me.membership_id,
  });
  expect(made.status).toBe(201);
  const task = made.json;

  // Opt in on this device
  await vol.goto("/en/field");
  await expect(vol.getByRole("heading", { name: "Offline field kit" })).toBeVisible();
  await expect(vol.getByText("Do not use a shared or public device.", { exact: false })).toBeVisible();
  await expectNoAxeViolations(vol);
  await vol.getByRole("button", { name: "Use this device for field work" }).click();
  await expect(vol.getByText(/Ready\. \d+ tasks? (is|are) saved on this device\./)).toBeVisible({ timeout: 30_000 });
  const card = vol.getByRole("listitem").filter({ hasText: `Offline check ${stamp}` });
  await expect(card).toBeVisible();

  // Lose the connection: the kit still opens and works from this device
  await vol.context().setOffline(true);
  await vol.reload();
  await expect(vol.getByText("Offline", { exact: true })).toBeVisible();
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Start" }).click();
  await expect(card.getByText("Not sent yet")).toBeVisible();
  await card.getByRole("button", { name: "Record a sighting" }).click();
  await vol.getByRole("dialog").getByLabel("Note").fill("Healthy, near the market gate");
  await vol.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  await expect(vol.getByText(/2 changes are saved on this device/)).toBeVisible();
  await expectNoAxeViolations(vol);
  const saved = await vol.evaluate(
    () =>
      new Promise<unknown[]>((resolve) => {
        const req = indexedDB.open("pawguard-field");
        req.onsuccess = () => {
          const all = req.result.transaction("queue").objectStore("queue").getAll();
          all.onsuccess = () => resolve(all.result);
        };
      }),
  );
  expect(saved).toHaveLength(2);

  // Reconnect: changes are sent automatically and applied once
  await vol.context().setOffline(false);
  await expect(vol.getByText("Sent: 2 applied, 0 need a decision, 0 not accepted.")).toBeVisible({ timeout: 30_000 });
  const after = await (await vol.context().request.get(`/api/v1/tasks/${task.id}`)).json();
  expect(after.state).toBe("in_progress");

  // Re-sending the same operations (e.g. a lost response) is recognised as a duplicate
  const ops = (saved as Record<string, unknown>[]).map(({ status, label, ...wire }) => wire);
  const dup = await apiPost(vol, "/api/v1/sync/operations", { device_id: "e2e-device-replay", operations: ops });
  expect(dup.status).toBe(200);
  expect(dup.json.results.every((r: { duplicate: boolean; state: string }) => r.duplicate && r.state === "accepted")).toBe(true);

  // Conflict: the coordinator cancels the task while the volunteer completes it offline
  await vol.context().setOffline(true);
  await card.getByRole("button", { name: "Complete" }).click();
  await vol.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  const fresh = await (await coord.context().request.get(`/api/v1/tasks/${task.id}`)).json();
  expect((await apiPost(coord, `/api/v1/tasks/${task.id}/transitions`, {
    action: "cancel", note: "Animal moved to the shelter", row_version: fresh.row_version,
  })).status).toBe(200);
  await vol.context().setOffline(false);
  await expect(vol.getByRole("heading", { name: "Changes that need your decision" })).toBeVisible({ timeout: 30_000 });
  await expect(vol.getByText("It is now: cancelled. Nothing was overwritten.", { exact: false })).toBeVisible();
  expect((await (await vol.context().request.get(`/api/v1/tasks/${task.id}`)).json()).state).toBe("cancelled");
  await expectNoAxeViolations(vol);
  await vol.screenshot({ path: path.resolve(import.meta.dirname, "../../docs/screenshots/phase8/field-kit-conflict-1280.png"), fullPage: true });

  // Signing out with an unresolved change warns, then removes all offline data from the device
  await vol.goto("/en/app");
  await vol.getByRole("button", { name: "Sign out" }).first().click();
  await expect(vol.getByRole("dialog").getByText(/1 change made offline was not sent/)).toBeVisible();
  await vol.getByRole("button", { name: "Sign out and delete them" }).click();
  await vol.waitForURL(/signed_out=1/);
  const leftovers = await vol.evaluate(async () => ({
    dbs: (await indexedDB.databases()).map((d) => d.name),
    caches: await caches.keys(),
    workers: (await navigator.serviceWorker.getRegistrations()).length,
  }));
  expect(leftovers.dbs).not.toContain("pawguard-field");
  expect(leftovers.caches.filter((k: string) => k.startsWith("pawguard-"))).toEqual([]);
  expect(leftovers.workers).toBe(0);
  await vol.context().close();
  await coord.context().close();
});
