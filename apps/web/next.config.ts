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
  // 'wasm-unsafe-eval': the certificate verifier's QR reader is WebAssembly. It allows compiling WebAssembly only
  // (JavaScript eval stays blocked) and must be site-wide: in-app navigation keeps the first page's policy.
  `script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'${isDev ? " 'unsafe-eval'" : ""}`,
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
  // Same-origin access to *signed* storage links only, used when the API hands out relative links
  // (PAWGUARD_STORAGE_SAME_ORIGIN=true, e.g. behind a public tunnel). Auth, database and other Supabase
  // endpoints are never forwarded; the signed token in each link still controls access.
  async rewrites() {
    const supabase = (process.env.PAWGUARD_SUPABASE_URL ?? "").replace(/\/$/, "");
    if (!supabase) return [];
    return [
      { source: "/storage/v1/object/sign/:path*", destination: `${supabase}/storage/v1/object/sign/:path*` },
      { source: "/storage/v1/object/upload/sign/:path*", destination: `${supabase}/storage/v1/object/upload/sign/:path*` },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // Microphone for voice questions to the assistant: our own pages only, and the browser still asks the
          // person. Site-wide because in-app navigation keeps the policy of the first page loaded.
          { key: "Permissions-Policy", value: "camera=(self), geolocation=(self), microphone=(self)" },
        ],
      },
    ];
  },
};

export default createNextIntlPlugin("./src/i18n/request.ts")(nextConfig);
