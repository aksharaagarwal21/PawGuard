"use client";

import { createApiClient, type ApiError } from "@pawguard/api-client";

import { CSRF_HEADER, readCsrfToken } from "./csrf";

/** Browser client: same-origin gateway (cookie session), CSRF header on every mutation. */
export const browserApi = createApiClient({ baseUrl: "" });
browserApi.use({
  onRequest({ request }) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      request.headers.set(CSRF_HEADER, readCsrfToken());
    }
    return request;
  },
});

export type FieldErrors = Record<string, string>;

/** Normalise an API error body into a code, message and per-field messages. */
export function parseApiError(error: unknown): { code: string; message: string; fields: FieldErrors } {
  const body = (error as ApiError | undefined)?.error;
  if (!body) return { code: "network_error", message: "", fields: {} };
  const fields: FieldErrors = {};
  for (const f of body.fields ?? []) fields[f.field] = f.message;
  return { code: body.code, message: body.message, fields };
}

/** RFC 4122 v4 UUID. Uses getRandomValues, which (unlike randomUUID) also works outside secure contexts. */
export function uuid4(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6]! & 0x0f) | 0x40;
  b[8] = (b[8]! & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export function newKey(): string {
  return uuid4();
}
