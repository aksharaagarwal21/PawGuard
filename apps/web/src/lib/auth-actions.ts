"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { z } from "zod";

import { serverEnv } from "./server-env";
import { getMe, ORG_COOKIE } from "./session";
import { createSupabaseServerClient } from "./supabase/server";

export type SignInState = { error?: "invalid" | "missing" | "unavailable" | "rateLimited"; email?: string };

const credentials = z.object({ email: z.string().trim().email().max(254), password: z.string().min(1).max(200) });

function safeLocale(v: FormDataEntryValue | null): string {
  return v === "ta" || v === "hi" ? v : "en";
}

export async function signIn(_prev: SignInState, form: FormData): Promise<SignInState> {
  const locale = safeLocale(form.get("locale"));
  const parsed = credentials.safeParse({ email: form.get("email"), password: form.get("password") });
  if (!parsed.success) return { error: "missing", email: String(form.get("email") ?? "") };
  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.auth.signInWithPassword(parsed.data);
  if (error) {
    if (error.status === 429) return { error: "rateLimited", email: parsed.data.email };
    if (error.status && error.status >= 500) return { error: "unavailable", email: parsed.data.email };
    return { error: "invalid", email: parsed.data.email };
  }
  redirect(`/${locale}/app`);
}

/** Development/demo only: sign in as a seeded fictional account. Refused unless demo mode is on. */
export async function demoSignIn(form: FormData): Promise<void> {
  const env = serverEnv();
  const locale = safeLocale(form.get("locale"));
  if (!env.demoMode) redirect(`/${locale}/sign-in`);
  const email = z.string().email().endsWith("@example.org").parse(form.get("email"));
  const supabase = await createSupabaseServerClient();
  // Published development credential for fictional seed accounts (see services/api seed/accounts.py).
  const { error } = await supabase.auth.signInWithPassword({ email, password: "PawGuard-demo-2026" });
  if (error) redirect(`/${locale}/sign-in?demo_error=1`);
  (await cookies()).delete(ORG_COOKIE);
  redirect(`/${locale}/app`);
}

export async function signOut(form: FormData): Promise<void> {
  const locale = safeLocale(form.get("locale"));
  const supabase = await createSupabaseServerClient();
  await supabase.auth.signOut({ scope: "local" }); // revokes this session's refresh token server-side
  (await cookies()).delete(ORG_COOKIE);
  redirect(`/${locale}/sign-in?signed_out=1`);
}

/** Choose the working organisation. The API re-verifies membership on every request regardless. */
export async function chooseOrganisation(form: FormData): Promise<void> {
  const locale = safeLocale(form.get("locale"));
  const orgId = z.string().uuid().parse(form.get("org_id"));
  const result = await getMe();
  if (result.state === "ok" && result.me.memberships.some((m) => m.org_id === orgId)) {
    (await cookies()).set(ORG_COOKIE, orgId, {
      httpOnly: true,
      sameSite: "lax",
      secure: serverEnv().secureCookies,
      path: "/",
      maxAge: 60 * 60 * 24 * 90,
    });
  }
  redirect(`/${locale}/app`);
}
