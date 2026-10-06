"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button, Field, Select, TextInput } from "@pawguard/ui";

import { useRouter } from "@/i18n/navigation";
import { browserApi, parseApiError } from "@/lib/api-browser";

const MAX = 2 * 1024 * 1024;

export function ImportUpload() {
  const t = useTranslations("imports");
  const router = useRouter();
  const [type, setType] = useState<"animals_csv" | "vaccinations_csv">("animals_csv");
  const [label, setLabel] = useState("");
  const [fmt, setFmt] = useState<"YYYY-MM-DD" | "DD/MM/YYYY" | "DD-MM-YYYY">("YYYY-MM-DD");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError(null);
    if (!file) return setError(t("chooseFile"));
    if (file.size > MAX) return setError(t("tooLarge"));
    if (label.trim().length < 3) return setError(t("labelRequired"));
    setBusy(true);
    const bytes = new Uint8Array(await file.arrayBuffer());
    let bin = "";
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    const { data, error: apiError } = await browserApi.POST("/api/v1/imports", {
      body: { import_type: type, source_label: label.trim(), filename: file.name, date_format: fmt, content_base64: btoa(bin) },
    });
    setBusy(false);
    if (data) {
      router.push(`/app/imports?id=${data.id}`);
      router.refresh();
      return;
    }
    setError(parseApiError(apiError).message || t("failed"));
  }

  return (
    <div className="space-y-4">
      <p className="text-ink-2">{t("uploadIntro")}</p>
      <Field id="import_type" label={t("type")}>
        {(aria) => (
          <Select {...aria} value={type} onChange={(e) => setType(e.target.value as typeof type)}>
            <option value="animals_csv">{t("types.animals_csv")}</option>
            <option value="vaccinations_csv">{t("types.vaccinations_csv")}</option>
          </Select>
        )}
      </Field>
      <p className="text-sm text-ink-2">{t(`columns.${type}`)}</p>
      <Field id="source_label" label={t("source")} hint={t("sourceHint")}>
        {(aria) => <TextInput {...aria} value={label} maxLength={200} onChange={(e) => setLabel(e.target.value)} />}
      </Field>
      <Field id="date_format" label={t("dateFormat")}>
        {(aria) => (
          <Select {...aria} value={fmt} onChange={(e) => setFmt(e.target.value as typeof fmt)}>
            {(["YYYY-MM-DD", "DD/MM/YYYY", "DD-MM-YYYY"] as const).map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </Select>
        )}
      </Field>
      <Field id="csv_file" label={t("file")} hint={t("fileHint")}>
        {(aria) => <input {...aria} type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block min-h-11" />}
      </Field>
      {error ? (
        <p role="alert" className="font-semibold text-urgent">
          {error}
        </p>
      ) : null}
      <Button onClick={submit} loading={busy}>
        {t("check")}
      </Button>
    </div>
  );
}
