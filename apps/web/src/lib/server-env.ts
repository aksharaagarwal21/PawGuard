import "server-only";

import { z } from "zod";

/**
 * Server-only configuration. Nothing here is `NEXT_PUBLIC_`; secrets never reach the browser bundle.
 * The publishable key is not secret, but the browser never uses Supabase directly (ADR 0002), so it stays
 * server-side too.
 */
const schema = z.object({
  PAWGUARD_ENV: z.enum(["development", "test", "staging", "production"]).default("development"),
  PAWGUARD_DEMO_MODE: z
    .string()
    .optional()
    .transform((v) => v === "true"),
  PAWGUARD_API_INTERNAL_URL: z.string().url(),
  PAWGUARD_WEB_ORIGIN: z.string().url(),
  PAWGUARD_SUPABASE_URL: z.string().url(),
  PAWGUARD_SUPABASE_PUBLIC_URL: z.string().url().optional(),
  PAWGUARD_SUPABASE_PUBLISHABLE_KEY: z.string().min(10),
  PAWGUARD_DEFAULT_TIMEZONE: z.string().default("UTC"),
  PAWGUARD_MAP_TILE_URL: z.string().optional(),
  PAWGUARD_MAP_TILE_ATTRIBUTION: z.string().optional(),
});

export type ServerEnv = z.infer<typeof schema> & { demoMode: boolean; secureCookies: boolean };

let cached: ServerEnv | null = null;

export function serverEnv(): ServerEnv {
  if (cached) return cached;
  const parsed = schema.parse(process.env);
  const demoMode = Boolean(parsed.PAWGUARD_DEMO_MODE) && parsed.PAWGUARD_ENV !== "production";
  if (parsed.PAWGUARD_ENV === "production" && parsed.PAWGUARD_DEMO_MODE) {
    throw new Error("PAWGUARD_DEMO_MODE must not be enabled in production");
  }
  cached = {
    ...parsed,
    demoMode,
    secureCookies: parsed.PAWGUARD_WEB_ORIGIN.startsWith("https://"),
  };
  return cached;
}
