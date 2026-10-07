"use client";

import type { Schemas } from "@pawguard/api-client";
import { AlertTriangle, BadgeCheck, CircleHelp, FileSearch, Info, RefreshCw, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { Button, cn } from "@pawguard/ui";

import { browserApi } from "@/lib/api-browser";

type Result = Schemas["EvidenceCheckOut"];
type Item = Result["files"][number]["checks"][number];

const ICON = { ok: BadgeCheck, warn: AlertTriangle, bad: XCircle, info: Info, unavailable: CircleHelp } as const;
const COLOUR = { ok: "text-primary", warn: "text-ink", bad: "text-urgent", info: "text-ink-2", unavailable: "text-ink-2" } as const;

/** AI-assisted evidence check beside the certificate: signed QR verification, reading + comparison with the record,
 *  and reuse of the same file. It assists the vet; nothing is verified or rejected automatically. */
export function EvidenceCheck({ eventId }: { eventId: string }) {
  const t = useTranslations("evidenceCheck");
  const [data, setData] = useState<Result | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const run = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    const { data: res } = await browserApi.GET("/api/v1/vaccination-events/{event_id}/evidence-check", {
      params: { path: { event_id: eventId } },
    });
    setLoading(false);
    if (res) setData(res);
    else setFailed(true);
  }, [eventId]);

  useEffect(() => {
    const id = window.setTimeout(() => void run(), 0);
    return () => window.clearTimeout(id);
  }, [run]);

  return (
    <section aria-labelledby={`ec-${eventId}`} className="space-y-3 rounded-card border border-divider bg-canvas p-4" data-testid="evidence-check">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={`ec-${eventId}`} className="flex items-center gap-2 text-base">
          <FileSearch aria-hidden className="size-5 text-primary" />
          {t("title")}
        </h3>
        <Button type="button" size="sm" variant="quiet" onClick={() => void run()} disabled={loading}>
          <RefreshCw aria-hidden className={cn("size-4", loading && "motion-safe:animate-spin")} />
          {t("rerun")}
        </Button>
      </div>
      {loading && !data ? <p role="status" className="text-sm text-ink-2">{t("checking")}</p> : null}
      {failed ? <p className="text-sm text-urgent">{t("failed")}</p> : null}
      {data ? (
        <>
          <p className={cn("text-sm font-semibold", data.summary === "problems" ? "text-urgent" : "")} data-summary={data.summary}>
            {t(`summary.${data.summary}`)}
          </p>
          {data.files.length === 0 ? <p className="text-sm text-ink-2">{t("noFiles")}</p> : null}
          {data.files.map((f, i) => (
            <div key={f.media_id} className="space-y-1.5">
              {data.files.length > 1 ? (
                <p className="text-xs font-semibold uppercase text-ink-2">{t("file", { n: i + 1, kind: t(`kind.${f.kind}`) })}</p>
              ) : null}
              <ul className="space-y-1.5">
                {f.checks.map((c: Item, j) => {
                  const Icon = ICON[c.status];
                  return (
                    <li key={j} className="flex gap-2 text-sm" data-check={c.kind} data-status={c.status}>
                      <Icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", COLOUR[c.status])} />
                      <span className={c.status === "bad" ? "font-semibold text-urgent" : undefined}>
                        {c.message}
                        {c.certificate ? (
                          <span className="block text-xs text-ink-2">
                            {t("signedDetail", {
                              pet: c.certificate.pet_name ?? c.certificate.pet_reference ?? "—",
                              vaccine: c.certificate.vaccine ?? "—",
                              given: c.certificate.given_on ?? "—",
                              vet: c.certificate.vet ?? "—",
                            })}
                          </span>
                        ) : null}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
          <p className="text-xs text-ink-2">{t("disclaimer")}</p>
        </>
      ) : null}
    </section>
  );
}
