"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button, ErrorSummary, Field, Notice, Select, TextInput } from "@pawguard/ui";

import { useRouter } from "@/i18n/navigation";
import { browserApi, parseApiError, type FieldErrors } from "@/lib/api-browser";

type Pet = { pet_id: string; pet_name: string; reference_code: string };
type Product = { id: string; name: string; template_interval_days?: number | null };

/** Vet records a vaccination given at the clinic (stored as verified, with the vet's next due date). */
export function ClinicRecordForm({ pets, products, today }: { pets: Pet[]; products: Product[]; today: string }) {
  const t = useTranslations("clinic.record");
  const tc = useTranslations("common");
  const router = useRouter();
  const [pet, setPet] = useState(pets[0]?.pet_id ?? "");
  const [product, setProduct] = useState(products[0]?.id ?? "");
  const [date, setDate] = useState(today);
  const [nextDue, setNextDue] = useState("");
  const [lot, setLot] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaved(false);
    const local: FieldErrors = {};
    if (!date) local.administered_on = t("dateRequired");
    else if (date > today) local.administered_on = t("dateFuture");
    if (nextDue && date && nextDue <= date) local.next_due_on = t("dueAfter");
    setErrors(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    const { error } = await browserApi.POST("/api/v1/clinic/vaccinations", {
      body: { animal_id: pet, product_id: product, administered_on: date, next_due_on: nextDue || null, lot_text: lot.trim() || null },
    });
    setBusy(false);
    if (error) {
      const p = parseApiError(error);
      setErrors(Object.keys(p.fields).length ? p.fields : { form: p.message || tc("tryAgainLater") });
      return;
    }
    setSaved(true);
    setNextDue("");
    setLot("");
    router.refresh();
  }

  const summary = Object.entries(errors)
    .filter(([f]) => f !== "form")
    .map(([f, message]) => ({ fieldId: `clinic-${f}`, message }));
  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      {summary.length ? <ErrorSummary title={tc("errorSummaryTitle")} errors={summary} /> : null}
      {saved ? <Notice tone="success" live="polite">{t("saved")}</Notice> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="clinic-animal_id" label={t("pet")}>
          {(aria) => (
            <Select {...aria} value={pet} onChange={(e) => setPet(e.target.value)}>
              {pets.map((p) => (
                <option key={p.pet_id} value={p.pet_id}>
                  {p.pet_name} ({p.reference_code})
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field id="clinic-product_id" label={t("vaccine")}>
          {(aria) => (
            <Select {...aria} value={product} onChange={(e) => setProduct(e.target.value)}>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.template_interval_days ? t("templateOption", { name: p.name, days: p.template_interval_days }) : p.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field id="clinic-administered_on" label={t("date")} error={errors.administered_on}>
          {(aria) => <TextInput {...aria} type="date" max={today} value={date} onChange={(e) => setDate(e.target.value)} />}
        </Field>
        <Field id="clinic-next_due_on" label={t("nextDue")} marker={tc("optional")} error={errors.next_due_on}>
          {(aria) => <TextInput {...aria} type="date" min={date} value={nextDue} onChange={(e) => setNextDue(e.target.value)} />}
        </Field>
      </div>
      <p className="text-sm text-ink-2">{t("nextDueHint")}</p>
      <Field id="clinic-lot_text" label={t("lot")} marker={tc("optional")}>
        {(aria) => <TextInput {...aria} value={lot} maxLength={40} onChange={(e) => setLot(e.target.value)} />}
      </Field>
      {errors.form ? <p className="font-semibold text-urgent">{errors.form}</p> : null}
      <Button type="submit" disabled={busy || !pet || !product}>
        {busy ? t("saving") : t("save")}
      </Button>
    </form>
  );
}
