"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button, Card, ErrorSummary, Field, RadioGroup, Select, TextInput, Textarea } from "@pawguard/ui";

import { LocationInput, type CapturedLocation } from "@/components/prevention/location-input";
import type { SubjectChoice } from "@/components/prevention/subject-picker";
import { Uploader } from "@/components/prevention/uploader";
import { useRouter } from "@/i18n/navigation";
import { browserApi, newKey, parseApiError } from "@/lib/api-browser";
import { todayIso } from "@/lib/format";

type Values = {
  species: "dog" | "cat" | "other" | "unknown";
  sex: "female" | "male" | "unknown";
  sterilisation_status: "sterilised" | "not_sterilised" | "unknown";
  age_band: "puppy" | "young" | "adult" | "senior" | "unknown";
  ownership_category: "owned" | "community" | "unowned" | "shelter" | "unknown";
  nickname: string;
  coat_description: string;
  identifying_marks: string;
  breed_note: string;
  area_id: string;
  observed_on: string;
};

export function NewAnimalForm({ areas, canUpload }: { areas: { id: string; name: string }[]; canUpload: boolean }) {
  const t = useTranslations("animalForm");
  const ta = useTranslations("animal");
  const tc = useTranslations("common");
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [v, setV] = useState<Values>({
    species: "dog",
    sex: "unknown",
    sterilisation_status: "unknown",
    age_band: "unknown",
    ownership_category: "unknown",
    nickname: "",
    coat_description: "",
    identifying_marks: "",
    breed_note: "",
    area_id: "",
    observed_on: todayIso(),
  });
  const [location, setLocation] = useState<CapturedLocation | null>(null);
  const [mediaIds, setMediaIds] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<{ fieldId: string; message: string }[]>([]);
  const idemKey = useRef(newKey());
  const opId = useRef(newKey());
  const headingRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const onMedia = useCallback((ids: string[]) => setMediaIds(ids), []);
  const [subjects, setSubjects] = useState<SubjectChoice[]>([]);
  const onSubjects = useCallback((c: SubjectChoice[]) => setSubjects(c), []);

  useEffect(() => {
    headingRef.current?.focus();
  }, [step]);
  useEffect(() => {
    if (errors.length) errorRef.current?.focus();
  }, [errors]);

  const set = <K extends keyof Values>(k: K) => (value: Values[K]) => setV((p) => ({ ...p, [k]: value }));
  const opt = (s: string) => (s.trim() ? s.trim() : null);

  async function save() {
    const needsReason = subjects.filter((s) => s.warnings.length && s.overrideReason.trim().length < 3);
    if (needsReason.length) {
      setStep(2);
      setErrors([{ fieldId: `override-${needsReason[0]!.mediaId}`, message: tc("reasonRequired") }]);
      return;
    }
    setSaving(true);
    setErrors([]);
    const hasObservation = Boolean(v.observed_on || location || v.area_id || mediaIds.length);
    const { data, error } = await browserApi.POST("/api/v1/animals", {
      headers: { "Idempotency-Key": idemKey.current },
      body: {
        species: v.species,
        sex: v.sex,
        sterilisation_status: v.sterilisation_status,
        age_band: v.age_band,
        ownership_category: v.ownership_category,
        nickname: opt(v.nickname),
        coat_description: opt(v.coat_description),
        identifying_marks: opt(v.identifying_marks),
        breed_note: opt(v.breed_note),
        home_area_id: v.area_id || null,
        client_operation_id: opId.current,
        first_observation: hasObservation
          ? {
              observed_on: v.observed_on || null,
              time_precision: v.observed_on ? "day" : "unknown",
              location,
              area_id: v.area_id || null,
              media_ids: mediaIds,
              subjects: subjects.map((s) => ({ media_id: s.mediaId, source: s.source, box: s.box, dog_count: s.dogCount })),
              quality_override_reason: subjects.map((s) => s.overrideReason.trim()).filter(Boolean).join("; ") || null,
            }
          : null,
      },
    });
    setSaving(false);
    if (data) {
      router.push(`/app/animals/${data.id}?created=1`);
      return;
    }
    const parsed = parseApiError(error);
    const list = Object.entries(parsed.fields).map(([field, message]) => ({ fieldId: field.split(".").pop() ?? field, message }));
    setErrors(list.length ? list : [{ fieldId: "save", message: parsed.message || t("errorSave") }]);
  }

  const steps = [t("steps.details"), t("steps.evidence"), t("steps.review")];
  const radio = (name: string, ns: string, values: string[]) =>
    values.map((value) => ({ value, label: ta(`${ns}.${value}`) }));

  return (
    <div className="space-y-5">
      <ol className="flex flex-wrap gap-2 text-sm" aria-label={t("stepOf", { step, total: 3 })}>
        {steps.map((label, i) => (
          <li
            key={label}
            aria-current={step === i + 1 ? "step" : undefined}
            className={`rounded-full px-3 py-1 font-display font-semibold ${step === i + 1 ? "bg-primary text-white" : step > i + 1 ? "bg-sage" : "bg-surface text-ink-2"}`}
          >
            {i + 1}. {label}
          </li>
        ))}
      </ol>
      <ErrorSummary ref={errorRef} title={tc("errorSummaryTitle")} errors={errors} />
      <Card className="space-y-5">
        <h2 ref={headingRef} tabIndex={-1} className="text-xl outline-none">
          {t("stepOf", { step })} — {steps[step - 1]}
        </h2>

        {step === 1 ? (
          <>
            <p className="text-ink-2">{t("detailsIntro")}</p>
            <RadioGroup name="species" legend={ta("species.label")} inline value={v.species} onChange={(x) => set("species")(x as Values["species"])} options={radio("species", "species", ["dog", "cat", "other", "unknown"])} />
            <RadioGroup name="sex" legend={ta("sex.label")} inline value={v.sex} onChange={(x) => set("sex")(x as Values["sex"])} options={radio("sex", "sex", ["female", "male", "unknown"])} />
            <RadioGroup name="sterilisation" legend={ta("sterilisation.label")} inline value={v.sterilisation_status} onChange={(x) => set("sterilisation_status")(x as Values["sterilisation_status"])} options={radio("sterilisation", "sterilisation", ["sterilised", "not_sterilised", "unknown"])} />
            <Field id="age_band" label={ta("ageBand.label")}>
              {(aria) => (
                <Select {...aria} value={v.age_band} onChange={(e) => set("age_band")(e.target.value as Values["age_band"])}>
                  {["unknown", "puppy", "young", "adult", "senior"].map((x) => (
                    <option key={x} value={x}>{ta(`ageBand.${x}`)}</option>
                  ))}
                </Select>
              )}
            </Field>
            <Field id="coat_description" label={ta("coat")} hint={ta("coatHint")} marker={tc("optional")}>
              {(aria) => <TextInput {...aria} maxLength={300} value={v.coat_description} onChange={(e) => set("coat_description")(e.target.value)} />}
            </Field>
            <Field id="identifying_marks" label={ta("marks")} hint={ta("marksHint")} marker={tc("optional")}>
              {(aria) => <Textarea {...aria} maxLength={500} value={v.identifying_marks} onChange={(e) => set("identifying_marks")(e.target.value)} />}
            </Field>
            <Field id="nickname" label={ta("nickname")} marker={tc("optional")}>
              {(aria) => <TextInput {...aria} maxLength={80} value={v.nickname} onChange={(e) => set("nickname")(e.target.value)} />}
            </Field>
            <Field id="ownership_category" label={ta("ownership.label")}>
              {(aria) => (
                <Select {...aria} value={v.ownership_category} onChange={(e) => set("ownership_category")(e.target.value as Values["ownership_category"])}>
                  {["unknown", "community", "owned", "unowned", "shelter"].map((x) => (
                    <option key={x} value={x}>{ta(`ownership.${x}`)}</option>
                  ))}
                </Select>
              )}
            </Field>
            <Field id="breed_note" label={ta("breed")} hint={ta("breedHint")} marker={tc("optional")}>
              {(aria) => <TextInput {...aria} maxLength={120} value={v.breed_note} onChange={(e) => set("breed_note")(e.target.value)} />}
            </Field>
          </>
        ) : null}

        {step === 2 ? (
          <>
            <p className="text-ink-2">{t("evidenceIntro")}</p>
            <Field id="area_id" label={t("area")}>
              {(aria) => (
                <Select {...aria} value={v.area_id} onChange={(e) => set("area_id")(e.target.value)}>
                  <option value="">{t("noArea")}</option>
                  {areas.map((a) => (
                    <option key={a.id} value={a.id}>{a.name}</option>
                  ))}
                </Select>
              )}
            </Field>
            <Field id="observed_on" label={t("when")}>
              {(aria) => <TextInput {...aria} type="date" max={todayIso()} value={v.observed_on} onChange={(e) => set("observed_on")(e.target.value)} />}
            </Field>
            <LocationInput value={location} onChange={setLocation} />
            {canUpload ? (
              <fieldset className="space-y-2">
                <legend className="font-display text-sm font-semibold">{t("photoOptional")}</legend>
                <Uploader purpose="animal_photo" onChange={onMedia} onSubjects={onSubjects} idPrefix="new-animal-photo" />
              </fieldset>
            ) : null}
          </>
        ) : null}

        {step === 3 ? (
          <>
            <p className="text-ink-2">{t("reviewIntro")}</p>
            <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-[12rem_1fr]">
              {(
                [
                  [ta("species.label"), ta(`species.${v.species}`)],
                  [ta("sex.label"), ta(`sex.${v.sex}`)],
                  [ta("sterilisation.label"), ta(`sterilisation.${v.sterilisation_status}`)],
                  [ta("ageBand.label"), ta(`ageBand.${v.age_band}`)],
                  [ta("coat"), v.coat_description || tc("notRecorded")],
                  [ta("marks"), v.identifying_marks || tc("notRecorded")],
                  [ta("nickname"), v.nickname || ta("noNickname")],
                  [ta("ownership.label"), ta(`ownership.${v.ownership_category}`)],
                  [t("area"), areas.find((a) => a.id === v.area_id)?.name ?? t("noArea")],
                  [t("when"), v.observed_on || tc("notRecorded")],
                ] as const
              ).map(([k, val]) => (
                <div key={k} className="contents">
                  <dt className="font-semibold">{k}</dt>
                  <dd className="text-ink-2">{val}</dd>
                </div>
              ))}
            </dl>
          </>
        ) : null}
      </Card>

      <div className="flex flex-wrap justify-between gap-3">
        {step > 1 ? (
          <Button type="button" variant="secondary" onClick={() => setStep(step - 1)}>
            {tc("back")}
          </Button>
        ) : (
          <span />
        )}
        {step < 3 ? (
          <Button type="button" onClick={() => setStep(step + 1)}>
            {tc("continue")}
          </Button>
        ) : (
          <Button type="button" onClick={save} loading={saving}>
            {saving ? t("saving") : t("save")}
          </Button>
        )}
      </div>
    </div>
  );
}
