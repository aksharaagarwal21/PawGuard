"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@pawguard/ui";

import { useRouter } from "@/i18n/navigation";
import { browserApi } from "@/lib/api-browser";

/** Regenerate (old QR stops working) or turn off the public card. */
export function CardActions({ petId, baseUrl }: { petId: string; baseUrl: string }) {
  const t = useTranslations("pets.card");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function regenerate() {
    if (!window.confirm(t("regenerateConfirm"))) return;
    setBusy(true);
    const { error } = await browserApi.POST("/api/v1/my/pets/{pet_id}/card/regenerate", {
      params: { path: { pet_id: petId }, query: { base_url: baseUrl } },
    });
    setBusy(false);
    setMessage(error ? t("failed") : t("regenerated"));
    router.refresh();
  }

  async function turnOff() {
    if (!window.confirm(t("turnOffConfirm"))) return;
    setBusy(true);
    const { error } = await browserApi.DELETE("/api/v1/my/pets/{pet_id}/card", { params: { path: { pet_id: petId } } });
    setBusy(false);
    setMessage(error ? t("failed") : t("turnedOff"));
    if (!error) router.push(`/app/pets/${petId}`);
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" disabled={busy} onClick={regenerate}>
          {t("regenerate")}
        </Button>
        <Button type="button" variant="secondary" disabled={busy} onClick={turnOff}>
          {t("turnOff")}
        </Button>
      </div>
      {message ? (
        <p role="status" className="text-sm font-semibold">
          {message}
        </p>
      ) : null}
    </div>
  );
}
