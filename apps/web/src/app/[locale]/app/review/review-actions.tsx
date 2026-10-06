"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button, Dialog, Field, TextInput, Textarea } from "@pawguard/ui";

import { useRouter } from "@/i18n/navigation";
import { browserApi, parseApiError } from "@/lib/api-browser";

type Outcome = "verified" | "needs_correction" | "rejected";

/** Verify / request correction / reject. Each needs explicit confirmation; the latter two need a reason. */
export function ReviewActions({
  eventId,
  rowVersion,
  nextId,
  suggestedNextDue = null,
}: {
  eventId: string;
  rowVersion: number;
  nextId?: string;
  /** From the certificate draft (OCR); the vet confirms or changes it. */
  suggestedNextDue?: string | null;
}) {
  const t = useTranslations("review");
  const tc = useTranslations("common");
  const router = useRouter();
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [reason, setReason] = useState("");
  const [nextDue, setNextDue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!outcome) return;
    if (outcome !== "verified" && reason.trim().length < 3) return setError(tc("reasonRequired"));
    setBusy(true);
    const { error: apiError } = await browserApi.POST("/api/v1/vaccination-events/{event_id}/reviews", {
      params: { path: { event_id: eventId } },
      body: {
        outcome,
        reason: reason.trim() || null,
        row_version: rowVersion,
        next_due_on: outcome === "verified" && nextDue ? nextDue : null,
      },
    });
    setBusy(false);
    if (apiError) {
      const p = parseApiError(apiError);
      if (p.code === "stale_row_version" || p.code === "invalid_state") {
        router.push("/app/review?stale=1");
        router.refresh();
        return;
      }
      return setError(p.fields.reason || p.fields.next_due_on || p.message || tc("tryAgainLater"));
    }
    setOutcome(null);
    router.push(nextId ? `/app/review?id=${nextId}&done=${outcome}` : `/app/review?done=${outcome}`);
    router.refresh();
  }

  const titles: Record<Outcome, string> = {
    verified: t("verifyConfirm"),
    needs_correction: t("correctionTitle"),
    rejected: t("rejectTitle"),
  };
  return (
    <div className="sticky bottom-20 flex flex-wrap gap-3 rounded-card border border-divider bg-surface p-4 shadow-card md:bottom-4">
      <Button onClick={() => { setError(null); setReason(""); setNextDue(suggestedNextDue ?? ""); setOutcome("verified"); }}>{t("verify")}</Button>
      <Button variant="secondary" onClick={() => { setError(null); setReason(""); setOutcome("needs_correction"); }}>
        {t("requestCorrection")}
      </Button>
      <Button variant="danger" onClick={() => { setError(null); setReason(""); setOutcome("rejected"); }}>
        {t("reject")}
      </Button>
      <Dialog
        open={outcome !== null}
        onOpenChange={(o) => !o && setOutcome(null)}
        title={outcome ? titles[outcome] : ""}
        description={outcome === "verified" ? t("verifyExplain") : undefined}
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setOutcome(null)}>
              {tc("cancel")}
            </Button>
            <Button onClick={submit} loading={busy} variant={outcome === "rejected" ? "danger" : "primary"}>
              {outcome === "verified" ? t("verify") : outcome === "rejected" ? t("reject") : t("requestCorrection")}
            </Button>
          </>
        }
      >
        {outcome && outcome !== "verified" ? (
          <Field id="review-reason" label={t("reasonLabel")} error={error ?? undefined}>
            {(aria) => <Textarea {...aria} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={2000} />}
          </Field>
        ) : (
          <>
            <Field
              id="review-next-due"
              label={t("nextDueLabel")}
              hint={suggestedNextDue ? `${t("nextDueFromCertificate")} ${t("nextDueHint")}` : t("nextDueHint")}
              marker={tc("optional")}
            >
              {(aria) => <TextInput {...aria} type="date" value={nextDue} onChange={(e) => setNextDue(e.target.value)} />}
            </Field>
            {error ? (
              <p role="alert" className="font-semibold text-urgent">
                {error}
              </p>
            ) : null}
          </>
        )}
      </Dialog>
    </div>
  );
}
