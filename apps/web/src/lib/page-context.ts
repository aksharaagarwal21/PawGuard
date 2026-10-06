import "server-only";

import { getLocale } from "next-intl/server";

import { redirect } from "@/i18n/navigation";

import { activeMembership, getMe, serverApi, type Me, type MembershipInfo } from "./session";

export type PageContext = {
  me: Me;
  active: MembershipInfo;
  api: Awaited<ReturnType<typeof serverApi>>;
  can: (cap: string) => boolean;
  locale: string;
  /** IANA timezone of the active organisation (for displaying instants). */
  tz: string;
};

/**
 * Authenticated page context. The layout already handles signed-out/unavailable states; this is a typed
 * shortcut for pages. `can` mirrors the API's capability check for *display only* — the API enforces.
 */
export async function pageContext(): Promise<PageContext> {
  const locale = await getLocale();
  const result = await getMe();
  if (result.state !== "ok") {
    redirect({ href: "/sign-in?expired=1", locale });
    throw new Error("unreachable");
  }
  const active = await activeMembership(result.me);
  if (!active) {
    redirect({ href: "/app", locale });
    throw new Error("unreachable");
  }
  const caps = new Set(active.capabilities);
  const scopes = new Set(active.professional_scopes);
  const can = (cap: string) =>
    caps.has(cap) && (cap !== "vaccination.review" || scopes.has("veterinary_review"));
  return { me: result.me, active, api: await serverApi(active.org_id), can, locale, tz: active.timezone };
}
