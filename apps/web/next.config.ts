import path from "node:path";

import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// Local development reads the repository-root .env (containers receive real environment variables instead).
// forceReload: Next has already loaded (and cached) env files from apps/web, which has none.
loadEnvConfig(path.resolve(import.meta.dirname, "../.."), process.env.NODE_ENV !== "production", undefined, true);

const supabasePublic = process.env.PAWGUARD_SUPABASE_PUBLIC_URL ?? process.env.PAWGUARD_SUPABASE_URL ?? "";
const tileOrigin = (() => {
  try {
    return process.env.PAWGUARD_MAP_TILE_URL ? new URL(process.env.PAWGUARD_MAP_TILE_URL.replaceAll(/[{}]/g, "")).origin : "";
  } catch {
    return "";
  }
})();
const isDev = process.env.NODE_ENV !== "production";

// Next.js App Router injects inline bootstrap scripts, so script-src needs 'unsafe-inline' until nonce-based CSP
// is added (tracked for Phase 14). Everything else is restricted to this origin plus Storage and map tiles.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob: ${supabasePublic} ${tileOrigin}`.trim(),
  "font-src 'self'",
  `connect-src 'self' ${supabasePublic} ${tileOrigin}${isDev ? " ws:" : ""}`.trim(),
  "worker-src 'self' blob:",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  transpilePackages: ["@pawguard/ui", "@pawguard/api-client"],
  outputFileTracingRoot: path.resolve(import.meta.dirname, "../.."),
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(self), geolocation=(self), microphone=()" },
        ],
      },
    ];
  },
};

export default createNextIntlPlugin("./src/i18n/request.ts")(nextConfig);
