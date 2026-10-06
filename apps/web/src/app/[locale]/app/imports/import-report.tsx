"use client";

import type { Schemas } from "@pawguard/api-client";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button, Card, Dialog, Field, Notice, StatusChip, Textarea } from "@pawguard/ui";

import { Link, useRouter } from "@/i18n/navigation";
import { browserApi, parseApiError } from "@/lib/api-browser";

type Job = Schemas["ImportDetail"];
type Row = { row: number; source_row_id: string; status: string; issues: { field: string; code: string; severity: string; message: string }[] };

const CHIP = { valid: "verified", warning: "submitted", rejected: "rejected", skip: "neutral" } as const;

export function ImportReport({ job, canRollback }: { job: Job; canRollback: boolean }) {
  const t = useTranslations("imports");
  const tc = useTranslations("common");
  const router = useRouter();
  const [includeWarnings, setIncludeWarnings] = useState(false);
  const [confirm, setConfirm] = useState<"apply" | "rollback" | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const report = job.report as { summary: Record<string, number>; rows: Row[]; mapping_version: string; dictionary_version: string };
  const toCreate = (report.summary.valid ?? 0) + (includeWarnings ? (report.summary.warning ?? 0) : 0);

  async function act() {
    setBusy(true);
    setError(null);
    const res =
      confirm === "apply"
        ? await browserApi.POST("/api/v1/imports/{import_id}/apply", {
            params: { path: { import_id: job.id } },
            body: { row_version: job.row_version, include_warning_rows: includeWarnings },
          })
        : await browserApi.POST("/api/v1/imports/{import_id}/rollback", {
            params: { path: { import_id: job.id } },
            body: { reason },
          });
    setBusy(false);
    if (res.error) return setError(parseApiError(res.error).message || tc("tryAgainLater"));
    setConfirm(null);
    router.refresh();
  }

  return (
    <Card className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg">{job.source_label}</h2>
        <Link href="/app/imports">{t("newImport")}</Link>
      </div>
      <p className="text-sm text-ink-2">
        {t(`types.${job.import_type}`)} · {job.raw_filename ?? ""} · {t("versions", { mapping: report.mapping_version, dictionary: report.dictionary_version })}
      </p>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {(["valid", "warning", "rejected", "skip"] as const).map((k) => (
          <div key={k} className="rounded-control bg-canvas p-3">
            <dt className="text-sm text-ink-2">{t(`rowStatus.${k}`)}</dt>
            <dd className="font-display text-2xl font-bold">{report.summary[k] ?? 0}</dd>
          </div>
        ))}
      </dl>
      {job.state === "validated" ? (
        <Notice tone="info" title={t("notAppliedTitle")}>
          <p>{t("notAppliedBody")}</p>
        </Notice>
      ) : (
        <Notice tone={job.state === "applied" ? "success" : "neutral"} title={t(`states.${job.state}`)} />
      )}
      <div className="max-h-112 overflow-auto rounded-control border border-divider">
        <table className="w-full min-w-xl text-left text-sm">
          <thead className="sticky top-0 bg-surface">
            <tr className="border-b border-divider">
              <th scope="col" className="p-2">{t("colRow")}</th>
              <th scope="col" className="p-2">{t("colSource")}</th>
              <th scope="col" className="p-2">{t("colStatus")}</th>
              <th scope="col" className="p-2">{t("colIssues")}</th>
            </tr>
          </thead>
          <tbody>
            {report.rows.map((r) => (
              <tr key={r.row} className="border-b border-divider align-top">
                <td className="p-2">{r.row}</td>
                <td className="p-2 font-mono">{r.source_row_id}</td>
                <td className="p-2">
                  <StatusChip kind={CHIP[r.status as keyof typeof CHIP] ?? "neutral"}>{t(`rowStatus.${r.status}`)}</StatusChip>
                </td>
                <td className="p-2">
                  <ul className="space-y-0.5">
                    {r.issues.map((i, n) => (
                      <li key={n}>
                        <span className="font-semibold">{i.field}</span>: {i.message}
                      </li>
                    ))}
                  </ul>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {job.state === "validated" ? (
        <div className="flex flex-wrap items-center gap-4">
          <label className="inline-flex min-h-11 items-center gap-2">
            <input type="checkbox" checked={includeWarnings} onChange={(e) => setIncludeWarnings(e.target.checked)} className="size-5 accent-primary" />
            {t("includeWarnings")}
          </label>
          <Button onClick={() => setConfirm("apply")} disabled={toCreate === 0}>
            {t("apply", { count: toCreate })}
          </Button>
        </div>
      ) : null}
      {job.state === "applied" && job.import_type === "animals_csv" && canRollback ? (
        <Button variant="secondary" onClick={() => setConfirm("rollback")}>
          {t("rollback")}
        </Button>
      ) : null}
      <Dialog
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm === "apply" ? t("applyConfirm", { count: toCreate }) : t("rollbackConfirm")}
        description={confirm === "apply" ? t("applyExplain") : t("rollbackExplain")}
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirm(null)}>
              {tc("cancel")}
            </Button>
            <Button onClick={act} loading={busy} variant={confirm === "rollback" ? "danger" : "primary"}>
              {tc("confirm")}
            </Button>
          </>
        }
      >
        {confirm === "rollback" ? (
          <Field id="rollback-reason" label={tc("reason")} error={error ?? undefined}>
            {(aria) => <Textarea {...aria} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />}
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
