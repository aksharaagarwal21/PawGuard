# ADR 0002 — Server-managed session; browser never holds tokens

Date: 2026-10-05 · Status: accepted

## Context
The brief prefers a same-origin, server-managed session so credentials are not exposed to application JavaScript, and requires CSRF protection for cookie-authenticated mutations. Supabase's SSR guide (checked 2026-10-05) says httpOnly cookies are "not recommended" because *its default design* lets the browser client read tokens.

## Decision
- No Supabase client is ever created in the browser. Sign-in/sign-out are Next.js server actions; `proxy.ts` refreshes the session with `@supabase/ssr`'s `createServerClient`, and every cookie it sets is forced to `httpOnly`, `SameSite=Lax`, `Secure` outside localhost, `Path=/`.
- Browser → `/api/v1/*` (Next.js route handler, same origin) → FastAPI with `Authorization: Bearer <access token>`. The gateway rejects mutations whose `Origin` is not the app origin and that lack a matching double-submit CSRF header (`X-PawGuard-CSRF` = value of the `pg_csrf` cookie).
- FastAPI verifies tokens itself (JWKS, `iss`, `aud`, `exp`, `role`) and never trusts the gateway's word.
- Sensitive commands also confirm the session is still live in `auth.sessions` (covers sign-out-everywhere and admin revocation before `exp`).

## Consequences
Token refresh happens only on server requests; a long-idle tab refreshes on its next navigation or gateway call. Direct-to-Storage uploads still work because they use a pre-signed URL, not the session. Deviation from the Supabase default is deliberate and must be re-checked when upgrading `@supabase/ssr`.
