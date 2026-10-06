"use client";

import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";

import { Button, ErrorSummary, Field, Notice, Select, TextInput } from "@pawguard/ui";

import { Uploader } from "@/components/prevention/uploader";
import { useRouter } from "@/i18n/navigation";
import { browserApi, parseApiError, type FieldErrors } from "@/lib/api-browser";

type Product = { id: string; name: string };
const OTHER = "__other__";

/**
 * An owner-entered vaccination with a certificate. It is always saved as "entered by owner (unverified)" and goes
 * to the clinic's vet for review. Used both to add a past vaccination and to mark a reminder as done.
 */
export function OwnerRecordForm({
  petId,
  clinicOrgId,
  products,
  today,
  reminder,
  onDone,
}: {
  petId: string;
  clinicOrgId: string;
  products: Product[];
  today: string;
  reminder?: { id: string; vaccine: string };
  onDone?: () => void;
}) {
  const t = useTranslations("pets.record");
  const tc = useTranslations("common");
  const router = useRouter();
  const preset = reminder ? products.find((p) => p.name === reminder.vaccine)?.id : undefined;
  const [product, setProduct] = useState(preset ?? products[0]?.id ?? OTHER);
  const [productText, setProductText] = useState("");
  const [date, setDate] = useState(today);
  const [givenBy, setGivenBy] = useState("");
  const [certs, setCerts] = useState<string[]>([]);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const onCerts = useCallback((ids: string[]) => setCerts(ids), []);
  const prefix = reminder ? `done-${reminder.id}` : `rec-${petId}`;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const local: FieldErrors = {};
    if (product === OTHER && !productText.trim()) local.product_id = t("vaccineRequired");
    if (!date) local.administered_on = t("dateRequired");
    else if (date > today) local.administered_on = t("dateFuture");
    if (certs.length === 0) local.certificate_media_ids = t("certificateRequired");
    setErrors(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    const body = {
      product_id: product === OTHER ? null : product,
      product_text: product === OTHER ? productText.trim() : null,
      administered_on: date,
      given_by: givenBy.trim() || null,
      certificate_media_ids: certs,
    };
    const { error } = reminder
      ? await browserApi.POST("/api/v1/my/reminders/{reminder_id}/done", { params: { path: { reminder_id: reminder.id } }, body })
      : await browserApi.POST("/api/v1/my/pets/{pet_id}/vaccinations", { params: { path: { pet_id: petId } }, body });
    setBusy(false);
    if (error) {
      const parsed = parseApiError(error);
      setErrors(Object.keys(parsed.fields).length ? parsed.fields : { form: parsed.message || tc("tryAgainLater") });
      return;
    }
    setSaved(true);
    onDone?.();
    router.refresh();
  }

  if (saved) return <Notice tone="success" live="polite">{t("saved")}</Notice>;
  const summary = Object.entries(errors)
    .filter(([field]) => field !== "form")
    .map(([field, message]) => ({ fieldId: `${prefix}-${field}`, message }));
  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <p className="text-sm text-ink-2">{t("unverifiedNote")}</p>
      {summary.length ? <ErrorSummary title={tc("errorSummaryTitle")} errors={summary} /> : null}
      <Field id={`${prefix}-product_id`} label={t("vaccine")} error={errors.product_id}>
        {(aria) => (
          <Select {...aria} value={product} onChange={(e) => setProduct(e.target.value)}>
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
            <option value={OTHER}>{t("otherVaccine")}</option>
          </Select>
        )}
      </Field>
      {product === OTHER ? (
        <Field id={`${prefix}-product_text`} label={t("vaccineName")}>
          {(aria) => <TextInput {...aria} value={productText} maxLength={200} onChange={(e) => setProductText(e.target.value)} />}
        </Field>
      ) : null}
      <Field id={`${prefix}-administered_on`} label={t("date")} error={errors.administered_on}>
        {(aria) => <TextInput {...aria} type="date" max={today} value={date} onChange={(e) => setDate(e.target.value)} />}
      </Field>
      <Field id={`${prefix}-given_by`} label={t("givenBy")} marker={tc("optional")}>
        {(aria) => <TextInput {...aria} value={givenBy} maxLength={200} onChange={(e) => setGivenBy(e.target.value)} />}
      </Field>
      <fieldset className="space-y-2" id={`${prefix}-certificate_media_ids`}>
        <legend className="font-display text-sm font-semibold">{t("certificate")}</legend>
        <p className="text-sm text-ink-2">{t("certificateHint")}</p>
        {errors.certificate_media_ids ? (
          <p className="text-sm font-semibold text-urgent">{errors.certificate_media_ids}</p>
        ) : null}
        <Uploader purpose="vaccination_evidence" allowPdf multiple idPrefix={`${prefix}-cert`} orgId={clinicOrgId} onChange={onCerts} />
      </fieldset>
      {errors.form ? <p className="font-semibold text-urgent">{errors.form}</p> : null}
      <Button type="submit" disabled={busy}>
        {busy ? t("saving") : reminder ? t("submitDone") : t("submit")}
      </Button>
    </form>
  );
}
