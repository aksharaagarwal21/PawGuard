import "server-only";

import { createApiClient, type Schemas } from "@pawguard/api-client";
import { cookies, headers } from "next/headers";
import { cache } from "react";

import { serverEnv } from "./server-env";
import { createSupabaseServerClient } from "./supabase/server";

export const ORG_COOKIE = "pg_org";

export type Me = Schemas["MeOut"];
export type MembershipInfo = Schemas["MembershipOut"];

/** Access token from the (proxy-refreshed) session cookie. Not trusted here — FastAPI verifies it. */
export const getAccessToken = cache(async (): Promise<string | null> => {
  const supabase = await createSupabaseServerClient();
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
});

export type MeResult =
  | { state: "signed_out" }
  | { state: "unavailable" }
  | { state: "ok"; me: Me; token: string };

/** The current user as the API sees them (capabilities from the database). Cached per request. */
export const getMe = cache(async (): Promise<MeResult> => {
  const token = await getAccessToken();
  if (!token) return { state: "signed_out" };
  try {
    const api = createApiClient({ baseUrl: serverEnv().PAWGUARD_API_INTERNAL_URL });
    const { data, response } = await api.GET("/api/v1/me", {
      headers: { Authorization: `Bearer ${token}`, "X-Request-ID": await requestId() },
      cache: "no-store",
    });
    if (response.status === 401) return { state: "signed_out" };
    if (!data) return { state: "unavailable" };
    return { state: "ok", me: data, token };
  } catch {
    return { state: "unavailable" };
  }
});

/** The organisation the user is working in: cookie choice if still a member, else the first membership. */
export async function activeMembership(me: Me): Promise<MembershipInfo | null> {
  const chosen = (await cookies()).get(ORG_COOKIE)?.value;
  return me.memberships.find((m) => m.org_id === chosen) ?? me.memberships[0] ?? null;
}

export async function requestId(): Promise<string> {
  const h = await headers();
  return h.get("x-request-id") ?? crypto.randomUUID().replaceAll("-", "");
}

/** Typed API client for Server Components, authenticated as the current user in their active organisation. */
export async function serverApi(orgId?: string) {
  const token = await getAccessToken();
  const api = createApiClient({ baseUrl: serverEnv().PAWGUARD_API_INTERNAL_URL });
  const rid = await requestId();
  api.use({
    onRequest({ request }) {
      if (token) request.headers.set("Authorization", `Bearer ${token}`);
      if (orgId) request.headers.set("X-PawGuard-Org", orgId);
      request.headers.set("X-Request-ID", rid);
      return request;
    },
  });
  return api;
}
