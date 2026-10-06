"use client";

import type { Schemas } from "@pawguard/api-client";
import { ScanText } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Button } from "@pawguard/ui";

import { browserApi, parseApiError } from "@/lib/api-browser";
import { formatPartialDate } from "@/lib/format";

export type CertificateDraft = Schemas["CertificateDraftOut"];

/** "Read the certificate": OCR draft to pre-fill the form. Always a draft — the person checks, a vet verifies. */
export function ReadCertificate({ mediaId, onDraft }: { mediaId: string | undefined; onDraft: (d: CertificateDraft) => void }) {
  const t = useTranslations("pets.ocr");
  const locale = useLocale();
  const [available, setAvailable] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<CertificateDraft | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const raf = requestAnimationFrame(async () => {
      const { data } = await browserApi.GET("/api/v1/ocr/status");
      setAvailable(Boolean(data?.available));
    });
    return () => cancelAnimationFrame(raf);
  }, []);

  if (!available || !mediaId) return null;

  async function read() {
    if (!mediaId) return;
    setBusy(true);
    setError(null);
    const { data, error: apiError } = await browserApi.POST("/api/v1/my/certificates/{media_id}/read", {
      params: { path: { media_id: mediaId } },
    });
    setBusy(false);
    if (!data) {
      const p = parseApiError(apiError);
      setError(t.has(`errors.${p.code}`) ? t(`errors.${p.code}`) : p.message || t("errors.generic"));
      return;
    }
    setDraft(data);
    onDraft(data);
  }

  const fmt = (d: string | null | undefined) => (d ? formatPartialDate(d, "day", locale, "") : null);
  return (
    <div className="space-y-2 rounded-control border border-dashed border-control p-3">
      <Button type="button" size="sm" variant="secondary" onClick={read} disabled={busy}>
        <ScanText aria-hidden className="size-4" />
        {busy ? t("reading") : t("read")}
      </Button>
      {error ? <p className="text-sm font-semibold text-urgent">{error}</p> : null}
      {draft ? (
        <div role="status" className="space-y-1 text-sm">
          <p className="font-semibold">{t("filled")}</p>
          <ul className="list-disc pl-5 text-ink-2">
            {draft.product_text ? <li>{t("vaccine", { name: draft.product_text })}</li> : <li>{t("noVaccine")}</li>}
            {draft.administered_on ? <li>{t("given", { date: fmt(draft.administered_on)! })}</li> : <li>{t("noDate")}</li>}
            {draft.lot_text ? <li>{t("lot", { lot: draft.lot_text })}</li> : null}
            {draft.next_due_on ? <li>{t("nextDue", { date: fmt(draft.next_due_on)! })}</li> : null}
          </ul>
          {draft.confidence !== null && draft.confidence !== undefined ? (
            <p className="text-xs text-ink-2">{t("confidence", { pct: Math.round(draft.confidence * 100) })}</p>
          ) : null}
          {draft.warnings.map((w) => (
            <p key={w} className="text-xs font-semibold">{w}</p>
          ))}
        </div>
      ) : (
        <p className="text-xs text-ink-2">{t("hint")}</p>
      )}
    </div>
  );
}
