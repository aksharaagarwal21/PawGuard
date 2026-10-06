"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button, Card, Field, Textarea } from "@pawguard/ui";

import { useRouter } from "@/i18n/navigation";
import { browserApi, parseApiError } from "@/lib/api-browser";

export function ProposeMerge({ sourceId, targetId }: { sourceId: string; targetId: string }) {
  const t = useTranslations("merge");
  const tc = useTranslations("common");
  const router = useRouter();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function propose() {
    if (reason.trim().length < 3) return setError(tc("reasonRequired"));
    setBusy(true);
    const { data, error: apiError } = await browserApi.POST("/api/v1/animal-merges", {
      body: { source_animal_id: sourceId, target_animal_id: targetId, reason: reason.trim() },
    });
    setBusy(false);
    if (data) {
      router.push(`/app/merges/${data.id}?proposed=1`);
      return;
    }
    setError(parseApiError(apiError).message || tc("tryAgainLater"));
  }

  return (
    <Card className="space-y-3">
      <Field id="merge-reason" label={t("reason")} error={error ?? undefined}>
        {(aria) => <Textarea {...aria} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} />}
      </Field>
      <Button onClick={propose} loading={busy}>
        {t("propose")}
      </Button>
    </Card>
  );
}
