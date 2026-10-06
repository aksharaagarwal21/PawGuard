import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

export const DEMO = {
  admin: { email: "admin.kavya@example.org", name: "Kavya" },
  volunteer: { email: "volunteer.priya@example.org", name: "Priya" },
  vet: { email: "vet.arun@example.org", name: "Dr Arun" },
  coordinator: { email: "coordinator.meena@example.org", name: "Meena" },
  hillVolunteer: { email: "volunteer.ravi@example.org", name: "Ravi" },
} as const;

export const DEMO_PASSWORD = "PawGuard-demo-2026";

export async function signIn(page: Page, email: string, locale = "en") {
  await page.goto(`/${locale}/sign-in`);
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(DEMO_PASSWORD);
  await page.locator('form button[type="submit"]').first().click();
  await page.waitForURL(`**/${locale}/app`);
}

/** WCAG 2.2 A/AA automated checks. Supplements, not replaces, manual keyboard/screen-reader review. */
export async function expectNoAxeViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  const summary = results.violations.map((v) => `${v.id} (${v.impact}): ${v.nodes.length} node(s) — ${v.help}`);
  expect(summary, summary.join("\n")).toEqual([]);
}

/** Deterministic demo organisation ids (seed/accounts.py). */
export const ORGS = {
  riverside: { id: "04e6d089-3750-505d-a6de-3813a6458fcb", label: "Demo — Riverside Animal Welfare Trust" },
} as const;

/** Make `org` the active organisation for a multi-membership account and wait until the server reflects it. */
export async function switchOrg(page: Page, org: { id: string; label: string }) {
  const switcher = page.locator('select[name="org_id"]');
  if (!(await switcher.count())) return;
  await switcher.first().selectOption({ label: org.label });
  await page.getByRole("button", { name: "Switch organisation" }).first().click();
  await expect(async () => {
    await page.reload();
    await expect(page.locator('select[name="org_id"]').first()).toHaveValue(org.id, { timeout: 1000 });
  }).toPass({ timeout: 15_000 });
}
