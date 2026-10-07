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
// The certificate verifier's fallback QR reader is WebAssembly (ZXing). 'wasm-unsafe-eval' allows compiling
// WebAssembly only — JavaScript eval stays blocked — and only on the verify page.
const verifyCsp = csp.replace("script-src 'self' 'unsafe-inline'", "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'");

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
          { key: "Permissions-Policy", value: "camera=(self), geolocation=(self), microphone=()" },
        ],
      },
      { source: "/:locale(en|ta|hi)/verify", headers: [{ key: "Content-Security-Policy", value: verifyCsp }] },
    ];
  },
};

export default createNextIntlPlugin("./src/i18n/request.ts")(nextConfig);
