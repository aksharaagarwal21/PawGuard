"use client";

import { useTranslations } from "next-intl";
import { useRef, useState } from "react";

import { Button, Card, Field, Select, TextInput, Textarea } from "@pawguard/ui";

import { useRouter } from "@/i18n/navigation";
import { browserApi, newKey, parseApiError } from "@/lib/api-browser";
import { todayIso } from "@/lib/format";

export function SurveyForm({
  areas,
  defaultArea,
  taskId,
  campaignId,
}: {
  areas: { id: string; name: string }[];
  defaultArea: string;
  taskId: string | null;
  campaignId: string | null;
}) {
  const t = useTranslations("survey");
  const tc = useTranslations("common");
  const router = useRouter();
  const op = useRef(newKey());
  const [area, setArea] = useState(defaultArea);
  const [date, setDate] = useState(todayIso());
  const [dogs, setDogs] = useState("");
  const [marked, setMarked] = useState("0");
  const [puppies, setPuppies] = useState("0");
  const [method, setMethod] = useState<"street_count" | "household" | "other">("street_count");
  const [notes, setNotes] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    const e: Record<string, string> = {};
    const n = Number(dogs);
    if (!area) e.area = t("chooseArea");
    if (dogs === "" || !Number.isInteger(n) || n < 0) e.dogs = t("wholeNumber");
    if (Number(marked) > n) e.marked = t("notMoreThanDogs");
    if (Number(puppies) > n) e.puppies = t("notMoreThanDogs");
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    setError(null);
    const { data, error: apiError } = await browserApi.POST("/api/v1/surveys", {
      body: {
        area_id: area,
        observed_on: date,
        dogs_counted: n,
        marked_count: Number(marked) || 0,
        puppies_count: Number(puppies) || 0,
        method,
        notes: notes.trim() || null,
        field_task_id: taskId,
        campaign_id: campaignId,
        client_operation_id: op.current,
      },
    });
    setBusy(false);
    if (data) {
      router.push("/app/tasks?saved=survey");
      router.refresh();
      return;
    }
    setError(parseApiError(apiError).message || tc("tryAgainLater"));
  }

  return (
    <Card className="space-y-4">
      <Field id="area" label={t("area")} error={errors.area}>
        {(aria) => (
          <Select {...aria} value={area} onChange={(e) => setArea(e.target.value)}>
            <option value="">{t("chooseArea")}</option>
            {areas.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </Select>
        )}
      </Field>
      <Field id="observed_on" label={t("date")}>
        {(aria) => <TextInput {...aria} type="date" max={todayIso()} value={date} onChange={(e) => setDate(e.target.value)} />}
      </Field>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field id="dogs" label={t("dogs")} hint={t("dogsHint")} error={errors.dogs}>
          {(aria) => <TextInput {...aria} inputMode="numeric" value={dogs} onChange={(e) => setDogs(e.target.value.replace(/\D/g, ""))} />}
        </Field>
        <Field id="marked" label={t("marked")} hint={t("markedHint")} error={errors.marked}>
          {(aria) => <TextInput {...aria} inputMode="numeric" value={marked} onChange={(e) => setMarked(e.target.value.replace(/\D/g, ""))} />}
        </Field>
        <Field id="puppies" label={t("puppies")} error={errors.puppies}>
          {(aria) => <TextInput {...aria} inputMode="numeric" value={puppies} onChange={(e) => setPuppies(e.target.value.replace(/\D/g, ""))} />}
        </Field>
      </div>
      <Field id="method" label={t("method")}>
        {(aria) => (
          <Select {...aria} value={method} onChange={(e) => setMethod(e.target.value as typeof method)}>
            <option value="street_count">{t("methods.street_count")}</option>
            <option value="household">{t("methods.household")}</option>
            <option value="other">{t("methods.other")}</option>
          </Select>
        )}
      </Field>
      <Field id="notes" label={t("notes")} marker={tc("optional")}>
        {(aria) => <Textarea {...aria} maxLength={1000} value={notes} onChange={(e) => setNotes(e.target.value)} />}
      </Field>
      <p className="text-sm text-ink-2">{t("notCensus")}</p>
      {error ? (
        <p role="alert" className="font-semibold text-urgent">
          {error}
        </p>
      ) : null}
      <Button onClick={save} loading={busy}>
        {t("save")}
      </Button>
    </Card>
  );
}
