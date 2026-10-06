import { expect, test } from "@playwright/test";

import { DEMO, signIn } from "./helpers";

/**
 * Session refresh happens server-side (proxy.ts) without exposing tokens to page scripts. To avoid waiting an
 * hour for real expiry, the test rewrites the stored session's `expires_at` into the past; @supabase/ssr must
 * then use the refresh token and write a new httpOnly cookie.
 */
function decode(value: string): Record<string, unknown> {
  const raw = value.startsWith("base64-") ? Buffer.from(value.slice(7), "base64url").toString("utf8") : value;
  return JSON.parse(raw);
}

test("an expired access token is refreshed server-side and the user stays signed in", async ({ page, context }) => {
  test.skip(test.info().project.name !== "desktop", "one run is enough");
  await signIn(page, DEMO.volunteer.email);
  const cookies = await context.cookies();
  const auth = cookies.filter((c) => /^sb-.*-auth-token(\.\d+)?$/.test(c.name));
  expect(auth, "single-chunk session cookie expected for this test").toHaveLength(1);
  const original = auth[0]!;
  const session = decode(original.value) as { access_token: string; expires_at: number };
  const oldAccess = session.access_token;
  session.expires_at = Math.floor(Date.now() / 1000) - 60;
  await context.addCookies([
    { ...original, value: "base64-" + Buffer.from(JSON.stringify(session)).toString("base64url") },
  ]);

  await page.goto("/en/app");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(`Hello, ${DEMO.volunteer.name}`);
  const refreshed = (await context.cookies()).find((c) => c.name === original.name)!;
  expect(refreshed.httpOnly).toBe(true);
  const next = decode(refreshed.value) as { access_token: string; expires_at: number };
  expect(next.access_token).not.toBe(oldAccess);
  expect(next.expires_at).toBeGreaterThan(Math.floor(Date.now() / 1000));
});

test("a tampered session cookie is not trusted", async ({ page, context }) => {
  test.skip(test.info().project.name !== "desktop", "one run is enough");
  await signIn(page, DEMO.volunteer.email);
  const original = (await context.cookies()).find((c) => /^sb-.*-auth-token$/.test(c.name))!;
  const session = decode(original.value) as { access_token: string; refresh_token: string };
  const [h, p] = session.access_token.split(".");
  const claims = JSON.parse(Buffer.from(p!, "base64url").toString("utf8"));
  claims.sub = "00000000-0000-0000-0000-000000000001"; // try to become someone else
  session.access_token = [h, Buffer.from(JSON.stringify(claims)).toString("base64url"), "invalidsig"].join(".");
  session.refresh_token = "invalid";
  await context.addCookies([{ ...original, value: "base64-" + Buffer.from(JSON.stringify(session)).toString("base64url") }]);
  await page.goto("/en/app");
  await expect(page).toHaveURL(/\/en\/sign-in/);
});
