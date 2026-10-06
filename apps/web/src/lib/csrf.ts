export const CSRF_COOKIE = "pg_csrf";
export const CSRF_HEADER = "x-pawguard-csrf";

/** Browser-side: read the double-submit token to echo in the CSRF header of gateway mutations. */
export function readCsrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${CSRF_COOKIE}=`));
  return match ? decodeURIComponent(match.slice(CSRF_COOKIE.length + 1)) : "";
}
