import { cookies } from "next/headers";
import { type NextRequest, NextResponse } from "next/server";

import { CSRF_COOKIE, CSRF_HEADER } from "@/lib/csrf";
import { ORG_COOKIE } from "@/lib/session";
import { serverEnv } from "@/lib/server-env";
import { createSupabaseServerClient } from "@/lib/supabase/server";

/**
 * Same-origin gateway: browser → /api/v1/* → FastAPI with the user's bearer token.
 * - Unsafe methods require a same-origin `Origin` and the double-submit CSRF header.
 * - The active organisation comes from the httpOnly `pg_org` cookie; FastAPI verifies membership itself.
 * - Only a fixed set of headers is forwarded each way.
 */
const FORWARD_REQUEST_HEADERS = ["content-type", "accept", "if-match", "idempotency-key", "x-request-id"];
const FORWARD_RESPONSE_HEADERS = ["content-type", "content-disposition", "etag", "x-request-id", "location", "retry-after"];
const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function errorJson(status: number, code: string, message: string) {
  return NextResponse.json({ error: { code, message, request_id: null, fields: [], details: {} } }, { status });
}

async function handle(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const env = serverEnv();
  const { path } = await ctx.params;
  if (path.some((seg) => seg === ".." || seg === "." || seg.includes("/") || seg.includes("\\"))) {
    return errorJson(400, "bad_path", "Invalid path.");
  }

  // Provider webhooks (e.g. WhatsApp) are server-to-server: no browser session or CSRF token. The API
  // authenticates them by the provider's signature, so the raw body and signature header are passed through.
  const webhook = path[0] === "webhooks";
  if (!SAFE.has(request.method) && !webhook) {
    const origin = request.headers.get("origin");
    const allowed = [env.PAWGUARD_WEB_ORIGIN, ...(env.PAWGUARD_EXTRA_WEB_ORIGINS ?? "").split(",")]
      .map((o) => o.trim())
      .filter(Boolean)
      .map((o) => new URL(o).origin);
    const store = await cookies();
    const csrfCookie = store.get(CSRF_COOKIE)?.value;
    if (!origin || !allowed.includes(origin) || !csrfCookie || request.headers.get(CSRF_HEADER) !== csrfCookie) {
      return errorJson(403, "csrf_failed", "This request could not be verified. Reload the page and try again.");
    }
  }

  const supabase = webhook ? null : await createSupabaseServerClient(); // may refresh and re-set cookies (allowed here)
  const token = supabase ? (await supabase.auth.getSession()).data.session?.access_token : undefined;

  const target = new URL(`/api/v1/${path.map(encodeURIComponent).join("/")}`, env.PAWGUARD_API_INTERNAL_URL);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  for (const name of webhook ? [...FORWARD_REQUEST_HEADERS, "x-hub-signature-256", "x-twilio-signature"] : FORWARD_REQUEST_HEADERS) {
    const v = request.headers.get(name);
    if (v) headers.set(name, v);
  }
  if (token) headers.set("authorization", `Bearer ${token}`);
  // A page may name the organisation explicitly (e.g. an owner uploading for a pet at another clinic). It is only
  // a selection: FastAPI checks the caller's membership in it on every request.
  const explicit = request.headers.get("x-pawguard-org");
  let org = webhook ? undefined : explicit && UUID_RE.test(explicit) ? explicit : (await cookies()).get(ORG_COOKIE)?.value;
  let resolvedOrg: string | undefined;
  const principalOnly = path.length === 1 && path[0] === "me"; // /me is about the person, not an organisation
  if (!org && token && !principalOnly) {
    // No explicit choice yet: use the same default as server-rendered pages (first active membership).
    resolvedOrg = await defaultOrg(env.PAWGUARD_API_INTERNAL_URL, token);
    org = resolvedOrg;
  }
  if (org) headers.set("x-pawguard-org", org);

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: SAFE.has(request.method) ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    return errorJson(503, "service_unavailable", "The PawGuard service could not be reached.");
  }

  const out = new NextResponse(upstream.body, { status: upstream.status });
  for (const name of FORWARD_RESPONSE_HEADERS) {
    const v = upstream.headers.get(name);
    if (v) out.headers.set(name, v);
  }
  out.headers.set("cache-control", "no-store");
  if (resolvedOrg) {
    out.cookies.set(ORG_COOKIE, resolvedOrg, {
      httpOnly: true,
      sameSite: "lax",
      secure: env.secureCookies,
      path: "/",
      maxAge: 60 * 60 * 24 * 90,
    });
  }
  return out;
}

async function defaultOrg(apiBase: string, token: string): Promise<string | undefined> {
  try {
    const r = await fetch(new URL("/api/v1/me", apiBase), {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    if (!r.ok) return undefined;
    const me = (await r.json()) as { memberships?: { org_id: string }[] };
    return me.memberships?.[0]?.org_id;
  } catch {
    return undefined;
  }
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
