import type { CookieOptions } from "@supabase/ssr";

/**
 * Every auth cookie is forced to httpOnly + SameSite=Lax (+ Secure on https). The browser never runs a
 * Supabase client, so no application JavaScript needs to read these tokens (ADR 0002).
 */
export function hardenCookie(options: CookieOptions | undefined, secure: boolean): CookieOptions {
  return { ...options, httpOnly: true, sameSite: "lax", secure, path: "/" };
}
