/**
 * Typed client for the PawGuard API. Types are generated from FastAPI's OpenAPI document
 * (`pnpm api-client:generate`); do not edit `schema.d.ts` by hand.
 */
import createClient, { type ClientOptions } from "openapi-fetch";

import type { components, paths } from "./schema";

export type { components, paths };
export type Schemas = components["schemas"];
export type ApiError = components["schemas"]["ErrorResponse"];

export function createApiClient(options: ClientOptions) {
  return createClient<paths>(options);
}
