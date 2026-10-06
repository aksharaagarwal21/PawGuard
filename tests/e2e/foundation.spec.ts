import { expect, test } from "@playwright/test";

import { DEMO, expectNoAxeViolations, signIn } from "./helpers";

test.describe("public access (no account)", () => {
  test("a visitor reaches urgent guidance and phone numbers without signing in", async ({ page }) => {
    await page.goto("/");
    // Demo builds open on the instructions page; real deployments on the landing page. Both offer urgent help.
    await expect(page).toHaveURL(/\/en(\/welcome)?$/);
    await page.getByRole("link", { name: "Get help after a bite" }).first().click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Bitten or scratched by an animal?");
    await expect(page.getByText("for at least 15 minutes")).toBeVisible();
    await expect(page.getByRole("link", { name: "112", exact: true })).toHaveAttribute("href", "tel:112");
    // No sign-in, photo upload or questionnaire on the help path.
    await expect(page.locator("main input, main textarea, main select")).toHaveCount(0);
    await expect(page.getByText("Not yet reviewed by a qualified local professional")).toBeVisible();
    await expectNoAxeViolations(page);
  });

  test("non-English help shows English health content with an untranslated notice", async ({ page }) => {
    await page.goto("/ta/help");
    // The notice itself is in the reader's language; the health wording stays in reviewed English.
    await expect(page.getByText("இந்த உள்ளடக்கம் இன்னும் உங்கள் மொழியில் கிடைக்கவில்லை", { exact: false })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", "ta");
    await expect(page.locator("article")).toHaveAttribute("lang", "en");
    await expect(page.getByText("for at least 15 minutes")).toBeVisible();
  });

  test("landing page has no accessibility violations and no forbidden claims", async ({ page }) => {
    await page.goto("/en");
    await expectNoAxeViolations(page);
    const text = (await page.locator("body").innerText()).toLowerCase();
    for (const forbidden of ["safe dog", "rabies-free", "% match", "ai verified", "endorsed by"]) {
      expect(text).not.toContain(forbidden);
    }
  });

  test("the app redirects anonymous visitors to sign in", async ({ page }) => {
    await page.goto("/en/app");
    await expect(page).toHaveURL(/\/en\/sign-in\?expired=1/);
  });
});

test.describe("sign-in and session", () => {
  test("wrong password shows an error and does not sign in", async ({ page }) => {
    await page.goto("/en/sign-in");
    await page.locator("#email").fill(DEMO.volunteer.email);
    await page.locator("#password").fill("wrong-password-123");
    await page.locator('form button[type="submit"]').first().click();
    await expect(page.locator("form").getByRole("alert")).toHaveText("The email address or password is not correct.");
    await expect(page).toHaveURL(/sign-in/);
  });

  test("auth cookies are httpOnly and the volunteer sees only permitted navigation", async ({ page, context }) => {
    await signIn(page, DEMO.volunteer.email);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(`Hello, ${DEMO.volunteer.name}`);
    const cookies = await context.cookies();
    const auth = cookies.filter((c) => c.name.startsWith("sb-"));
    expect(auth.length).toBeGreaterThan(0);
    for (const c of auth) {
      expect(c.httpOnly, `${c.name} must be httpOnly`).toBe(true);
      expect(c.sameSite).toBe("Lax");
    }
    // Field volunteers have no system.view capability: the item is absent and the page is forbidden.
    await expect(page.getByRole("link", { name: "System status" })).toHaveCount(0);
    await page.goto("/en/app/system");
    await expect(page.getByText("You don't have access to this page")).toBeVisible();
    await expectNoAxeViolations(page);
  });

  test("an administrator sees provider status without secret values", async ({ page }) => {
    await signIn(page, DEMO.admin.email);
    await page.goto("/en/app/system");
    await expect(page.getByRole("heading", { name: "System status" })).toBeVisible();
    await expect(page.getByText("identity_matching")).toBeVisible();
    // Either no identity model, or a research model that has not passed the release gate — never "available".
    await expect(page.getByText(/No identity model is active\.|has not passed the release gate/)).toBeVisible();
    const html = await page.content();
    expect(html).not.toMatch(/sb_secret_|service_role|postgresql:\/\//);
    await expectNoAxeViolations(page);
  });

  test("sign out ends the session", async ({ page, isMobile }) => {
    await signIn(page, DEMO.volunteer.email);
    if (isMobile) await page.goto("/en/app/more");
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/signed_out=1/);
    await page.goto("/en/app");
    await expect(page).toHaveURL(/\/en\/sign-in/);
  });
});

test.describe("gateway protections", () => {
  test("mutations without the CSRF header are rejected", async ({ page }) => {
    await signIn(page, DEMO.volunteer.email);
    const status = await page.evaluate(async () => {
      const r = await fetch("/api/v1/me", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ preferred_name: "x", row_version: 1 }),
      });
      return r.status;
    });
    expect(status).toBe(403);
  });

  test("reads through the gateway use the server-side session", async ({ page }) => {
    await signIn(page, DEMO.vet.email);
    const body = await page.evaluate(async () => (await fetch("/api/v1/me")).json());
    expect(body.email).toBe(DEMO.vet.email);
    expect(body.memberships[0].professional_scopes).toContain("veterinary_review");
  });
});
