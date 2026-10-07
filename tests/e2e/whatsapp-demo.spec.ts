import { expect, test, type Page } from "@playwright/test";

import { DEMO, expectNoAxeViolations, signIn } from "./helpers";

/** Clinic demo tools → WhatsApp demo (Twilio trial). Nothing here sends a real message: the first test only reads
 * the panel, and the second answers every WhatsApp demo request with fixed data. */

const panel = (page: Page) => page.getByTestId("whatsapp-demo");

test("WhatsApp demo panel shows setup state and the masked recipient, never credentials", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await signIn(page, DEMO.clinicVet.email);
  await page.goto("/en/app/clinic");
  await expect(panel(page).getByRole("heading", { name: "WhatsApp (Twilio trial)" })).toBeVisible();
  await expect(panel(page)).toContainText("••••1527");
  await expect(panel(page)).toContainText("generic Twilio trial template");
  const html = await page.content();
  expect(html).not.toMatch(/AC[0-9a-f]{32}/); // no account SID
  expect(html).not.toMatch(/\d{6}\s?1527/); // only the masked recipient (••••1527) reaches the browser
  await expectNoAxeViolations(page);
});

const now = Date.now();
const iso = (minutes: number) => new Date(now + minutes * 60_000).toISOString();
const item = (over: Record<string, unknown>) => ({
  id: crypto.randomUUID(),
  kind: "test",
  state: "sent",
  scheduled_for: iso(-30),
  created_at: iso(-30),
  sent_at: iso(-30),
  attempts: 1,
  message_sid: null,
  provider_status: null,
  provider_status_at: iso(-29),
  error_code: null,
  explanation: null,
  recipient_masked: "••••1527",
  ...over,
});
const fixture = {
  ready: true,
  missing: [],
  recipient_masked: "••••1527",
  callback_url: "https://example.trycloudflare.com/api/v1/webhooks/twilio/status",
  template_body: "Reminder: Appt Tue Oct 29, 3:00 PM. Reply C to confirm or R to reschedule. Test message from Twilio.",
  template_sample: "sample",
  sends_left_this_hour: 3,
  history: [
    item({ kind: "demo_reminder", state: "queued", scheduled_for: iso(2), sent_at: null, attempts: 0, provider_status_at: null }),
    item({ message_sid: "SM00000000000000000000000000000001", provider_status: "read" }),
    item({ kind: "demo_reminder", message_sid: "SM00000000000000000000000000000002", provider_status: "delivered" }),
    item({
      state: "failed",
      message_sid: "SM00000000000000000000000000000003",
      provider_status: "undelivered",
      error_code: "63015",
      explanation: "The recipient hasn't joined the Twilio trial sender (send the join code from that phone first). (Twilio error 63015)",
    }),
    item({ kind: "demo_reminder", state: "skipped", sent_at: null, explanation: "Cancelled before sending" }),
  ],
};

test("WhatsApp demo history, failure explanations, IST times and double-click protection", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let posts = 0;
  await page.route("**/api/v1/clinic/whatsapp-demo", (route) => route.fulfill({ json: fixture }));
  await page.route("**/api/v1/clinic/whatsapp-demo/test", async (route) => {
    posts += 1;
    await new Promise((r) => setTimeout(r, 800));
    await route.fulfill({ status: 202, json: { id: crypto.randomUUID(), scheduled_for: iso(0) } });
  });
  await page.route("**/api/v1/clinic/whatsapp-demo/schedule", (route) =>
    route.fulfill({
      status: 409,
      json: { error: { code: "already_queued", message: "One is already waiting to be sent — see the history below.", request_id: "x" } },
    }),
  );
  await signIn(page, DEMO.clinicVet.email);
  await page.goto("/en/app/clinic");
  const p = panel(page);
  await expect(p.getByRole("heading", { name: "WhatsApp (Twilio trial)" })).toBeVisible();
  await expect(p.getByTestId("wa-template-preview")).toContainText("Test message from Twilio.");
  await expect(p).toContainText("exact text Twilio reported");
  const history = p.getByTestId("wa-history");
  await expect(history).toContainText("Scheduled");
  await expect(history).toContainText("Read on the phone");
  await expect(history).toContainText("Delivered to the phone");
  await expect(history).toContainText("Not delivered");
  await expect(history).toContainText("hasn't joined the Twilio trial sender");
  await expect(history).toContainText("Cancelled before sending");
  await expect(history.getByRole("button", { name: "Cancel" })).toHaveCount(1);
  const expectedIst = new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" })
    .format(new Date(fixture.history[1].scheduled_for))
    .replace(/\s/g, " ");
  await expect(history).toContainText("IST");
  expect((await history.textContent())?.replace(/\s/g, " ")).toContain(expectedIst.split(" ")[0]);

  const send = p.getByRole("button", { name: "Send test WhatsApp" });
  // A double click (two clicks in the same tick, before React re-renders the button) sends one request.
  await send.evaluate((b: HTMLButtonElement) => {
    b.click();
    b.click();
  });
  await expect(p.getByRole("status")).toContainText("Queued");
  expect(posts).toBe(1);

  await p.getByRole("button", { name: "Schedule a practice reminder in 2 minutes" }).click();
  await expect(p.getByRole("status")).toContainText("already waiting");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expectNoAxeViolations(page);
  await p.screenshot({ path: "test-results/notify/whatsapp-demo-390.png" });
});
