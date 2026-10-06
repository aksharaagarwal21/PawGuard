"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button, Card, ErrorSummary, Field, RadioGroup, Select, TextInput, Textarea } from "@pawguard/ui";

import { Uploader } from "@/components/prevention/uploader";
import { useRouter } from "@/i18n/navigation";
import { browserApi, newKey, parseApiError } from "@/lib/api-browser";
import { todayIso } from "@/lib/format";

type Precision = "day" | "month" | "year" | "unknown";
export type Product = { id: string; name: string };
export type Lot = { id: string; product_id: string; lot_number: string };
export type Initial = {
  date_precision?: string;
  administered_on?: string | null;
  product_id?: string | null;
  product_text?: string | null;
  lot_id?: string | null;
  lot_text?: string | null;
  administered_by_name?: string | null;
  administered_by_registration?: string | null;
  area_id?: string | null;
  submitter_note?: string | null;
};

/**
 * Vaccination evidence entry. Every field except the animal can be "not known"; the reviewer sees exactly what
 * was and wasn't recorded. Submit means "submitted for review", never verified. In amend mode the form posts a
 * corrected record that supersedes the original (the original is kept).
 */
export function VaccinationForm({
  animalId,
  products,
  lots,
  areas,
  amend,
  initial,
}: {
  animalId: string;
  products: Product[];
  lots: Lot[];
  areas: { id: string; name: string }[];
  amend?: { eventId: string; rowVersion: number };
  initial?: Initial;
}) {
  const t = useTranslations("vaccForm");
  const tc = useTranslations("common");
  const router = useRouter();
  const init = initial ?? {};
  const [precision, setPrecision] = useState<Precision>((["day", "month", "year", "unknown"].includes(init.date_precision ?? "") ? init.date_precision : "day") as Precision);
  const [day, setDay] = useState(init.administered_on ?? "");
  const [month, setMonth] = useState(init.administered_on?.slice(0, 7) ?? "");
  const [year, setYear] = useState(init.administered_on?.slice(0, 4) ?? "");
  const [productChoice, setProductChoice] = useState(init.product_id ?? (init.product_text ? "__text" : products.length ? "" : "__unknown"));
  const [productText, setProductText] = useState(init.product_text ?? "");
  const [lotChoice, setLotChoice] = useState(init.lot_id ?? (init.lot_text ? "__text" : "__unknown"));
  const [lotText, setLotText] = useState(init.lot_text ?? "");
  const [by, setBy] = useState(init.administered_by_name ?? "");
  const [reg, setReg] = useState(init.administered_by_registration ?? "");
  const [area, setArea] = useState(init.area_id ?? "");
  const [note, setNote] = useState("");
  const [evidence, setEvidence] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<{ fieldId: string; message: string }[]>([]);
  const idem = useRef(newKey());
  const op = useRef(newKey());
  const errRef = useRef<HTMLDivElement>(null);
  const onEvidence = useCallback((ids: string[]) => setEvidence(ids), []);
  useEffect(() => {
    if (errors.length) errRef.current?.focus();
  }, [errors]);

  const productLots = useMemo(() => lots.filter((l) => l.product_id === productChoice), [lots, productChoice]);

  function administeredOn(): string | null {
    if (precision === "day") return day || null;
    if (precision === "month") return month ? `${month}-01` : null;
    if (precision === "year") return year ? `${year}-01-01` : null;
    return null;
  }

  async function submit() {
    const date = administeredOn();
    const local: { fieldId: string; message: string }[] = [];
    if (precision !== "unknown" && !date) local.push({ fieldId: "administered_on", message: t("date") });
    if (productChoice === "__text" && !productText.trim()) local.push({ fieldId: "product_text", message: t("productText") });
    if (lotChoice === "__text" && !lotText.trim()) local.push({ fieldId: "lot_text", message: t("lotText") });
    if (local.length) return setErrors(local);
    setBusy(true);
    setErrors([]);
    const body = {
      animal_id: animalId,
      date_precision: precision,
      administered_on: date,
      product_id: productChoice && !productChoice.startsWith("__") ? productChoice : null,
      product_text: productChoice === "__text" ? productText.trim() : null,
      lot_id: lotChoice && !lotChoice.startsWith("__") ? lotChoice : null,
      lot_text: lotChoice === "__text" ? lotText.trim() : null,
      administered_by_name: by.trim() || null,
      administered_by_registration: reg.trim() || null,
      area_id: area || null,
      submitter_note: note.trim() || null,
      evidence_media_ids: evidence,
      source_type: evidence.length ? ("certificate_upload" as const) : ("field_entry" as const),
      client_operation_id: op.current,
    };
    const result = amend
      ? await browserApi.POST("/api/v1/vaccination-events/{event_id}/amendments", {
          params: { path: { event_id: amend.eventId } },
          body: { ...body, row_version: amend.rowVersion },
        })
      : await browserApi.POST("/api/v1/vaccination-events", { headers: { "Idempotency-Key": idem.current }, body });
    setBusy(false);
    if (result.data) {
      router.push(`/app/vaccinations/${result.data.id}?submitted=1`);
      return;
    }
    const p = parseApiError(result.error);
    const list = Object.entries(p.fields).map(([f, m]) => ({ fieldId: f.split(".").pop() ?? f, message: m }));
    setErrors(list.length ? list : [{ fieldId: "submit", message: p.code === "stale_row_version" ? tc("changedElsewhere") : p.message || tc("tryAgainLater") }]);
  }

  return (
    <div className="space-y-5">
      <ErrorSummary ref={errRef} title={tc("errorSummaryTitle")} errors={errors} />
      <p className="text-sm text-ink-2">{t("unknownAllowed")}</p>
      <Card className="space-y-5">
        <RadioGroup
          name="date_precision"
          legend={t("dateSection")}
          inline
          value={precision}
          onChange={(x) => setPrecision(x as Precision)}
          options={(["day", "month", "year", "unknown"] as const).map((p) => ({ value: p, label: t(`precision.${p}`) }))}
        />
        {precision === "day" ? (
          <Field id="administered_on" label={t("date")}>
            {(aria) => <TextInput {...aria} type="date" max={todayIso()} value={day} onChange={(e) => setDay(e.target.value)} />}
          </Field>
        ) : null}
        {precision === "month" ? (
          <Field id="administered_on" label={t("month")}>
            {(aria) => <TextInput {...aria} type="month" max={todayIso().slice(0, 7)} value={month} onChange={(e) => setMonth(e.target.value)} />}
          </Field>
        ) : null}
        {precision === "year" ? (
          <Field id="administered_on" label={t("year")}>
            {(aria) => <TextInput {...aria} type="number" inputMode="numeric" min={1990} max={new Date().getFullYear()} value={year} onChange={(e) => setYear(e.target.value)} />}
          </Field>
        ) : null}
      </Card>

      <Card className="space-y-5">
        <Field id="product_id" label={t("product")}>
          {(aria) => (
            <Select {...aria} value={productChoice} onChange={(e) => { setProductChoice(e.target.value); setLotChoice("__unknown"); }}>
              <option value="__unknown">{t("productUnknown")}</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
              <option value="__text">{t("productNotListed")}</option>
            </Select>
          )}
        </Field>
        {productChoice === "__text" ? (
          <Field id="product_text" label={t("productText")}>
            {(aria) => <TextInput {...aria} maxLength={200} value={productText} onChange={(e) => setProductText(e.target.value)} />}
          </Field>
        ) : null}
        <Field id="lot_id" label={t("lot")}>
          {(aria) => (
            <Select {...aria} value={lotChoice} onChange={(e) => setLotChoice(e.target.value)}>
              <option value="__unknown">{t("lotUnknown")}</option>
              {productLots.map((l) => (
                <option key={l.id} value={l.id}>{l.lot_number}</option>
              ))}
              <option value="__text">{t("lotNotListed")}</option>
            </Select>
          )}
        </Field>
        {lotChoice === "__text" ? (
          <Field id="lot_text" label={t("lotText")}>
            {(aria) => <TextInput {...aria} maxLength={40} value={lotText} onChange={(e) => setLotText(e.target.value)} />}
          </Field>
        ) : null}
        <Field id="administered_by_name" label={t("administeredBy")} marker={tc("optional")}>
          {(aria) => <TextInput {...aria} maxLength={200} value={by} onChange={(e) => setBy(e.target.value)} />}
        </Field>
        <Field id="administered_by_registration" label={t("registration")} marker={tc("optional")}>
          {(aria) => <TextInput {...aria} maxLength={100} value={reg} onChange={(e) => setReg(e.target.value)} />}
        </Field>
        <Field id="area_id" label={t("area")} marker={tc("optional")}>
          {(aria) => (
            <Select {...aria} value={area} onChange={(e) => setArea(e.target.value)}>
              <option value="">{tc("notRecorded")}</option>
              {areas.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </Select>
          )}
        </Field>
      </Card>

      <Card className="space-y-3">
        <h2 className="text-base">{t("evidence")}</h2>
        <p className="text-sm text-ink-2">{t("evidenceHint")}</p>
        <Uploader purpose="vaccination_evidence" multiple allowPdf onChange={onEvidence} idPrefix="vacc-evidence" />
      </Card>

      <Card>
        <Field id="submitter_note" label={t("note")} hint={t("noteHint")} marker={tc("optional")}>
          {(aria) => <Textarea {...aria} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />}
        </Field>
      </Card>

      <p className="rounded-card bg-sand p-4">{t("whatNext")}</p>
      <div className="flex justify-end">
        <Button onClick={submit} loading={busy} size="lg">
          {busy ? t("submitting") : t("submit")}
        </Button>
      </div>
    </div>
  );
}
