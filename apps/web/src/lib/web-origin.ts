import "server-only";

import { headers } from "next/headers";

/** The origin the visitor used (works behind the local tunnel), for links printed in QR codes. */
export async function requestOrigin(): Promise<string> {
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "localhost:3000";
  const proto = h.get("x-forwarded-proto") ?? (host.startsWith("localhost") || host.startsWith("127.") ? "http" : "https");
  return `${proto.split(",")[0]!.trim()}://${host.split(",")[0]!.trim()}`;
}
