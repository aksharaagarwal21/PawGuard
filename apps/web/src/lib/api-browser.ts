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

export function newKey(): string {
  return crypto.randomUUID();
}
