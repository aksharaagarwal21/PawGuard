import { expect, test, type Page } from "@playwright/test";

import { DEMO, expectNoAxeViolations, signIn } from "./helpers";

/** "This pet bit someone": first aid first (en/ta/hi, 390 px), the report and private links, the owner's daily
 *  update, the clinic view — and the wording rules. Reports use Bruno's existing demo bite date, so they join that
 *  observation and no new owner alert is sent. */

const FORBIDDEN = /\bsafe\b|rabies[- ]free|no treatment (is )?needed/i;
const WASH = { en: "15 minutes", ta: "15 நிமிடங்கள்", hi: "15 मिनट" } as const;

async function brunoCardToken(page: Page): Promise<string> {
  await signIn(page, DEMO.owner.email);
  const pets = await (await page.request.get("/api/v1/my/pets")).json();
  const bruno = (pets.items ?? pets).find((p: { name: string }) => p.name === "Bruno");
  const card = await (await page.request.get(`/api/v1/my/pets/${bruno.id}/card`)).json();
  await page.context().clearCookies();
  return card.token as string;
}

async function bodyText(page: Page) {
  return (await page.locator("body").innerText()).replace(/\s+/g, " ");
}

test("bite mode shows first aid before anything else, in English, Tamil and Hindi", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const token = await brunoCardToken(page);
  await page.goto(`/en/card/${token}`);
  await expect(page.getByTestId("bite-button")).toBeVisible();
  for (const locale of ["en", "ta", "hi"] as const) {
    await page.goto(`/${locale}/card/${token}/bite`);
    const firstAid = page.getByTestId("first-aid");
    await expect(firstAid).toContainText(WASH[locale]);
    // First aid is the first thing in the page content, and above the vaccination record.
    expect(await page.locator("main > div > :first-child").getAttribute("data-testid")).toBe("first-aid");
    const fa = await firstAid.boundingBox();
    const status = await page.getByTestId("bite-status").boundingBox();
    expect(fa && status && fa.y < status.y).toBe(true);
    await expect(page.getByRole("link", { name: /112/ })).toBeVisible();
    expect(FORBIDDEN.test(await bodyText(page))).toBe(false);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
  await page.goto(`/en/card/${token}/bite`);
  await expect(page.getByTestId("bite-cert-genuine")).toBeVisible({ timeout: 20_000 }); // Part 1 check inline
  await expect(page.getByText("Show this screen to your doctor. Your doctor decides your treatment.")).toBeVisible();
  await expectNoAxeViolations(page);
});

test("report a bite, follow it privately, make and revoke a doctor link", async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 390, height: 844 });
  const token = await brunoCardToken(page);
  const brunoBite = new Date(Date.now() - 4 * 86_400_000).toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
  await page.goto(`/en/card/${token}/bite`);
  await page.getByLabel("Date of the bite").fill(brunoBite);
  await page.getByRole("button", { name: "Send report" }).click();
  const created = page.getByTestId("bite-created");
  await expect(created).toContainText("Save this link to see updates.");
  await expect(created).toContainText("already reported a bite by this pet on that day"); // joined the demo case
  const url = (await page.getByTestId("tracking-url").textContent())!.trim();

  await page.goto(url);
  expect(await page.locator("main > div > :first-child").getAttribute("data-testid")).toBe("first-aid");
  await expect(page.getByRole("heading", { name: /Your bite report BR-/ })).toBeVisible();
  const timeline = page.getByTestId("observation");
  await expect(timeline.locator("[data-day-status=no_update]").first()).toContainText("No update");
  expect(FORBIDDEN.test(await bodyText(page))).toBe(false);
  await expect(page.getByText("owner.neha")).toHaveCount(0);

  await page.getByRole("button", { name: "Make a doctor link" }).click();
  const doctorUrl = (await page.getByTestId("doctor-url").textContent())!.trim();
  const doctor = await page.context().newPage();
  await doctor.goto(doctorUrl);
  await expect(doctor.getByText("Owner reports are not vet-verified unless marked.")).toBeVisible();
  await expect(doctor.getByRole("button", { name: "Make a doctor link" })).toHaveCount(0);
  expect(FORBIDDEN.test(await bodyText(doctor))).toBe(false);

  await page.getByRole("button", { name: "Turn off all doctor links" }).click();
  await expect(page.getByText("Doctor links turned off.")).toBeVisible();
  await doctor.reload();
  await expect(doctor.getByText("This link doesn't work")).toBeVisible();
});

test("owner's daily update, urgent banners for the reporter and the clinic", async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, DEMO.owner.email);
  await page.goto("/en/app/pets");
  await expect(page.getByTestId("bite-banner").first()).toBeVisible();
  await page.goto("/en/app/bites");
  const misty = page.getByTestId("bite-case").filter({ hasText: "Misty" });
  await expect(misty).toContainText("Contact your vet now");
  await misty.getByLabel("Unusual behaviour").check();
  await misty.getByRole("button", { name: "Save today's update" }).click();
  await expect(misty).toContainText("Today's update is saved.");
  expect(FORBIDDEN.test(await bodyText(page))).toBe(false);

  await page.goto("/en/bite/pawguard-demo-reporter-link-misty-0002");
  await expect(page.getByTestId("urgent-banner")).toContainText("Tell your doctor right away.");
  await page.goto("/en/bite/pawguard-demo-reporter-link-bruno-0001");
  await expect(page.getByTestId("observation").locator("[data-day-status=no_update]")).toHaveCount(1);

  await page.context().clearCookies();
  await signIn(page, DEMO.clinicVet.email);
  await page.goto("/en/app/clinic");
  const section = page.getByTestId("clinic-bites");
  await expect(section.locator("li").first()).toHaveAttribute("data-urgent", "true");
  await expect(section).toContainText("Change reported");
  await expect(section).not.toContainText("@"); // no reporter contact details
});
