import "server-only";

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

import { serverEnv } from "../server-env";
import { hardenCookie } from "./cookies";

/**
 * Supabase client for Server Components, Server Actions and Route Handlers. In Server Components cookie
 * writes are not allowed; token refresh there is handled by proxy.ts before rendering.
 */
export async function createSupabaseServerClient() {
  const env = serverEnv();
  const store = await cookies();
  return createServerClient(env.PAWGUARD_SUPABASE_URL, env.PAWGUARD_SUPABASE_PUBLISHABLE_KEY, {
    cookies: {
      getAll() {
        return store.getAll();
      },
      setAll(list) {
        try {
          for (const { name, value, options } of list) {
            store.set(name, value, hardenCookie(options, env.secureCookies));
          }
        } catch {
          // Called from a Server Component: ignore; proxy.ts refreshes sessions.
        }
      },
    },
  });
}
