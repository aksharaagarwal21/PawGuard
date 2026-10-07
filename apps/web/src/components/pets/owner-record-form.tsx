"use client";

import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";

import { Button, ErrorSummary, Field, Notice, Select, TextInput, cn } from "@pawguard/ui";

import { Uploader } from "@/components/prevention/uploader";
import { useRouter } from "@/i18n/navigation";
import { browserApi, parseApiError, type FieldErrors } from "@/lib/api-browser";

import { ReadCertificate, type CertificateDraft } from "./read-certificate";
import { ReviewList, StepProgress } from "./stepper";

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
  clinicName,
  stepped = false,
}: {
  petId: string;
  clinicOrgId: string;
  products: Product[];
  today: string;
  reminder?: { id: string; vaccine: string };
  onDone?: () => void;
  /** Shown in the success message ("… will check this record"). */
  clinicName?: string;
  /** Three steps with a review (pet page); the quick "mark as done" form on a reminder stays on one screen. */
  stepped?: boolean;
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
  const [rejected, setRejected] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [step, setStep] = useState(0);
  const onCerts = useCallback((ids: string[]) => {
    setCerts(ids);
    setRejected(null);
  }, []);
  // OCR draft from the certificate: pre-fills vaccine and date for the person to check.
  function applyDraft(d: CertificateDraft) {
    const match = d.product_id ? products.find((p) => p.id === d.product_id) : undefined;
    if (match) setProduct(match.id);
    else if (d.product_text) {
      setProduct(OTHER);
      setProductText(d.product_text);
    }
    if (d.administered_on && d.administered_on <= today) setDate(d.administered_on);
  }
  const prefix = reminder ? `done-${reminder.id}` : `rec-${petId}`;

  function validate(upTo: number): FieldErrors {
    const local: FieldErrors = {};
    if (product === OTHER && !productText.trim()) local.product_id = t("vaccineRequired");
    if (!date) local.administered_on = t("dateRequired");
    else if (date > today) local.administered_on = t("dateFuture");
    if (upTo >= 1 && certs.length === 0) local.certificate_media_ids = t("certificateRequired");
    return local;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (stepped && step < 2) {
      const local = validate(step);
      setErrors(local);
      if (!Object.keys(local).length) setStep((s) => s + 1);
      return;
    }
    const local = validate(2);
    setErrors(local);
    if (Object.keys(local).length) {
      if (stepped) setStep(local.certificate_media_ids && Object.keys(local).length === 1 ? 1 : 0);
      return;
    }
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
      if (parsed.code === "evidence_rejected") {
        // The automatic check stopped it before it reached the vet: back to the certificate, with the reasons.
        setRejected(parsed.fields.certificate_media_ids ?? parsed.message);
        setErrors({});
        if (stepped) setStep(1);
        return;
      }
      setErrors(Object.keys(parsed.fields).length ? parsed.fields : { form: parsed.message || tc("tryAgainLater") });
      return;
    }
    setRejected(null);
    setSaved(true);
    onDone?.();
    router.refresh();
  }

  if (saved)
    return (
      <Notice tone="success" live="polite">
        <p>{t("saved")}</p>
        <p>{clinicName ? t("savedNext", { clinic: clinicName }) : t("savedNextGeneric")}</p>
      </Notice>
    );
  const productName = product === OTHER ? productText.trim() : products.find((p) => p.id === product)?.name ?? "";
  const summary = Object.entries(errors)
    .filter(([field]) => field !== "form")
    .map(([field, message]) => ({ fieldId: `${prefix}-${field}`, message }));
  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      {stepped ? <StepProgress step={step + 1} total={3} title={t(`steps.${["details", "certificate", "review"][step]}`)} /> : null}
      <p className="text-sm text-ink-2">{t("unverifiedNote")}</p>
      {summary.length ? <ErrorSummary title={tc("errorSummaryTitle")} errors={summary} /> : null}
      <div className={cn("space-y-4", stepped && step !== 0 && "hidden")}>
      <Field id={`${prefix}-product_id`} label={t("vaccine")} hint={t("vaccineHint")} error={errors.product_id}>
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
      <Field id={`${prefix}-administered_on`} label={t("date")} hint={t("dateHint")} error={errors.administered_on}>
        {(aria) => <TextInput {...aria} type="date" max={today} value={date} onChange={(e) => setDate(e.target.value)} />}
      </Field>
      <Field id={`${prefix}-given_by`} label={t("givenBy")} hint={t("givenByHint")} marker={tc("optional")}>
        {(aria) => <TextInput {...aria} value={givenBy} maxLength={200} onChange={(e) => setGivenBy(e.target.value)} />}
      </Field>
      </div>
      <fieldset className={cn("space-y-2", stepped && step !== 1 && "hidden")} id={`${prefix}-certificate_media_ids`}>
        <legend className="font-display text-sm font-semibold">{t("certificate")}</legend>
        <p className="text-sm text-ink-2">{t("certificateHint")}</p>
        {errors.certificate_media_ids ? (
          <p className="text-sm font-semibold text-urgent">{errors.certificate_media_ids}</p>
        ) : null}
        {rejected ? (
          <Notice tone="urgent" title={t("rejectedTitle")} live="alert">
            <p>{rejected}</p>
            <p className="mt-1 text-sm">{t("rejectedNext")}</p>
          </Notice>
        ) : null}
        <Uploader purpose="vaccination_evidence" allowPdf multiple idPrefix={`${prefix}-cert`} orgId={clinicOrgId} onChange={onCerts} />
        <ReadCertificate mediaId={certs[0]} onDraft={applyDraft} />
      </fieldset>
      {stepped && step === 2 ? (
        <ReviewList
          rows={[
            [t("vaccine"), productName],
            [t("date"), date],
            [t("givenBy"), givenBy.trim() || tc("notRecorded")],
            [t("certificate"), t("certificateCount", { count: certs.length })],
          ]}
        />
      ) : null}
      {errors.form ? <p className="font-semibold text-urgent">{errors.form}</p> : null}
      <div className="flex flex-wrap gap-3">
        {stepped && step > 0 ? (
          <Button type="button" variant="secondary" onClick={() => setStep((s) => s - 1)}>
            {tc("back")}
          </Button>
        ) : null}
        <Button type="submit" disabled={busy}>
          {stepped && step < 2 ? tc("continue") : busy ? t("checking") : reminder ? t("submitDone") : t("submit")}
        </Button>
      </div>
    </form>
  );
}
