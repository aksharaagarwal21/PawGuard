import { createServerClient, type CookieOptions } from "@supabase/ssr";
import createIntlMiddleware from "next-intl/middleware";
import type { NextRequest } from "next/server";

import { routing } from "./i18n/routing";
import { CSRF_COOKIE } from "./lib/csrf";
import { serverEnv } from "./lib/server-env";
import { hardenCookie } from "./lib/supabase/cookies";

const intl = createIntlMiddleware(routing);

/**
 * Runs before page rendering:
 * 1. Refreshes the Supabase session (only when an auth cookie exists — anonymous visitors cause no Auth call).
 *    Updated cookies are written to the request too, so Server Components in this request see fresh tokens
 *    (next-intl forwards the request headers).
 * 2. Locale routing (next-intl).
 * 3. Issues the double-submit CSRF cookie used by the /api/v1 gateway.
 * Authorisation is NOT decided here; pages and the API check it themselves.
 */
export default async function proxy(request: NextRequest) {
  const env = serverEnv();
  const pending: { name: string; value: string; options: CookieOptions }[] = [];
  let cacheHeaders: Record<string, string> = {};

  if (request.cookies.getAll().some((c) => c.name.startsWith("sb-"))) {
    const supabase = createServerClient(env.PAWGUARD_SUPABASE_URL, env.PAWGUARD_SUPABASE_PUBLISHABLE_KEY, {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll(list, headers) {
          for (const c of list) {
            request.cookies.set(c.name, c.value);
            pending.push(c);
          }
          cacheHeaders = (headers as Record<string, string> | undefined) ?? {};
        },
      },
    });
    try {
      await supabase.auth.getClaims();
    } catch {
      // Auth temporarily unreachable: continue rendering; pages will show a signed-out or error state.
    }
  }

  const response = intl(request);
  for (const c of pending) response.cookies.set(c.name, c.value, hardenCookie(c.options, env.secureCookies));
  for (const [k, v] of Object.entries(cacheHeaders)) response.headers.set(k, v);
  if (!request.cookies.get(CSRF_COOKIE)) {
    response.cookies.set(CSRF_COOKIE, crypto.randomUUID(), {
      httpOnly: false, // read by our own same-origin script and echoed in a header
      sameSite: "strict",
      secure: env.secureCookies,
      path: "/",
    });
  }
  return response;
}

export const config = {
  matcher: "/((?!api|storage|_next|_vercel|.*\\..*).*)",
};
