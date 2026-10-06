"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button, Card, Field, Textarea, useToast } from "@pawguard/ui";

import { useRouter } from "@/i18n/navigation";
import { browserApi, parseApiError } from "@/lib/api-browser";

export function MergeDecision({ mergeId, state }: { mergeId: string; state: string }) {
  const t = useTranslations("merge");
  const tc = useTranslations("common");
  const router = useRouter();
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function act(action: "approve" | "reject" | "reverse") {
    if (reason.trim().length < 3) return setError(tc("reasonRequired"));
    setBusy(action);
    const path = `/api/v1/animal-merges/{merge_id}/${action}` as const;
    const { error: apiError } = await browserApi.POST(path, { params: { path: { merge_id: mergeId } }, body: { reason: reason.trim() } });
    setBusy(null);
    if (apiError) return setError(parseApiError(apiError).message || tc("tryAgainLater"));
    toast({ title: t(`states.${action === "approve" ? "executed" : action === "reject" ? "rejected" : "reversed"}`), tone: "success" });
    setReason("");
    router.refresh();
  }

  return (
    <Card className="space-y-3">
      <Field id="decision-reason" label={t("decisionReason")} error={error ?? undefined}>
        {(aria) => <Textarea {...aria} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} />}
      </Field>
      <div className="flex flex-wrap gap-2">
        {state === "proposed" ? (
          <>
            <Button onClick={() => act("approve")} loading={busy === "approve"}>
              {t("approve")}
            </Button>
            <Button variant="secondary" onClick={() => act("reject")} loading={busy === "reject"}>
              {t("reject")}
            </Button>
          </>
        ) : (
          <Button variant="danger" onClick={() => act("reverse")} loading={busy === "reverse"}>
            {t("reverse")}
          </Button>
        )}
      </div>
    </Card>
  );
}
