"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button, Card, Dialog, Field, Textarea, useToast } from "@pawguard/ui";

import { Link, useRouter } from "@/i18n/navigation";
import { browserApi, parseApiError } from "@/lib/api-browser";

type Target = "reviewed" | "active" | "disputed" | "archived";

/** Profile-level actions. Buttons appear per capability; the API re-checks every action. */
export function ProfileActions({
  animalId,
  referenceCode,
  profileState,
  rowVersion,
  canWrite,
  canMerge,
}: {
  animalId: string;
  referenceCode: string;
  profileState: string;
  rowVersion: number;
  canWrite: boolean;
  canMerge: boolean;
}) {
  const t = useTranslations("profile");
  const tc = useTranslations("common");
  const router = useRouter();
  const toast = useToast();
  const [dialog, setDialog] = useState<{ to: Target; title: string; help?: string; needsReason: boolean } | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (["merged_alias", "archived"].includes(profileState)) return null;

  async function submit() {
    if (!dialog) return;
    if (dialog.needsReason && reason.trim().length < 3) {
      setError(tc("reasonRequired"));
      return;
    }
    setBusy(true);
    const { error: apiError } = await browserApi.POST("/api/v1/animals/{animal_id}/profile-transitions", {
      params: { path: { animal_id: animalId } },
      body: { to_state: dialog.to, reason: reason.trim() || null, row_version: rowVersion },
    });
    setBusy(false);
    if (apiError) {
      const p = parseApiError(apiError);
      setError(p.code === "stale_row_version" ? tc("changedElsewhere") : p.fields.reason || p.message);
      return;
    }
    toast({ title: dialog.to === "disputed" ? t("reportSent") : t("transitionDone"), tone: "success" });
    setDialog(null);
    setReason("");
    router.refresh();
  }

  const open = (to: Target, title: string, needsReason: boolean, help?: string) => {
    setError(null);
    setReason("");
    setDialog({ to, title, needsReason, help });
  };

  return (
    <Card className="h-fit space-y-3">
      {canWrite && profileState !== "disputed" ? (
        <Button variant="secondary" block onClick={() => open("disputed", t("reportIncorrect"), true, t("reportIncorrectHelp"))}>
          {t("reportIncorrect")}
        </Button>
      ) : null}
      {canWrite ? (
        <Button asChild variant="secondary" block>
          <Link href={`/app/merges/new?source=${animalId}`}>{t("possibleDuplicate")}</Link>
        </Button>
      ) : null}
      {canMerge && profileState === "provisional" ? (
        <Button block onClick={() => open("reviewed", t("markReviewed"), false)}>
          {t("markReviewed")}
        </Button>
      ) : null}
      {canMerge && profileState === "reviewed" ? (
        <Button block onClick={() => open("active", t("markActive"), false)}>
          {t("markActive")}
        </Button>
      ) : null}
      {canMerge && profileState === "disputed" ? (
        <Button block onClick={() => open("reviewed", t("resolveDispute"), true)}>
          {t("resolveDispute")}
        </Button>
      ) : null}
      {canMerge ? (
        <Button variant="quiet" block onClick={() => open("archived", t("archive"), true, t("archiveHelp"))}>
          {t("archive")}
        </Button>
      ) : null}

      <Dialog
        open={dialog !== null}
        onOpenChange={(o) => !o && setDialog(null)}
        title={dialog ? `${dialog.title} — ${referenceCode}` : ""}
        description={dialog?.help}
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDialog(null)}>
              {tc("cancel")}
            </Button>
            <Button onClick={submit} loading={busy} variant={dialog?.to === "archived" ? "danger" : "primary"}>
              {tc("confirm")}
            </Button>
          </>
        }
      >
        {dialog?.needsReason ? (
          <Field id="profile-reason" label={tc("reason")} error={error ?? undefined}>
            {(aria) => <Textarea {...aria} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} />}
          </Field>
        ) : error ? (
          <p role="alert" className="font-semibold text-urgent">
            {error}
          </p>
        ) : null}
      </Dialog>
    </Card>
  );
}
