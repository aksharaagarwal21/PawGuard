"use client";

import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";

import { Button, ErrorSummary, Field, RadioGroup, Select, TextInput, cn } from "@pawguard/ui";

import { Uploader } from "@/components/prevention/uploader";
import { useRouter } from "@/i18n/navigation";
import { browserApi, parseApiError, type FieldErrors } from "@/lib/api-browser";

import { ReviewList, StepProgress } from "./stepper";

type Clinic = { org_id: string; name: string };
const STEPS = ["about", "clinic", "review"] as const;

/** Add a pet in three short steps: about your pet → clinic and photo → check and save. */
export function PetForm({ clinics, today }: { clinics: Clinic[]; today: string }) {
  const t = useTranslations("pets.form");
  const tp = useTranslations("pets");
  const tc = useTranslations("common");
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [clinic, setClinic] = useState(clinics[0]?.org_id ?? "");
  const [name, setName] = useState("");
  const [species, setSpecies] = useState<"dog" | "cat">("dog");
  const [sex, setSex] = useState<"female" | "male" | "unknown">("unknown");
  const [dob, setDob] = useState("");
  const [photo, setPhoto] = useState<string[]>([]);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);
  const onPhoto = useCallback((ids: string[]) => setPhoto(ids), []);

  function validate(upTo: number): FieldErrors {
    const local: FieldErrors = {};
    if (upTo >= 0) {
      if (!name.trim()) local.name = t("nameRequired");
      if (dob && dob > today) local.date_of_birth = t("dobFuture");
    }
    if (upTo >= 1 && !clinic) local.clinic_org_id = t("clinicRequired");
    return local;
  }

  function next() {
    const local = validate(step);
    setErrors(local);
    if (!Object.keys(local).length) setStep((s) => Math.min(s + 1, STEPS.length - 1));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (step < STEPS.length - 1) return next();
    const local = validate(STEPS.length);
    setErrors(local);
    if (Object.keys(local).length) return setStep(local.name || local.date_of_birth ? 0 : 1);
    setBusy(true);
    const { data, error } = await browserApi.POST("/api/v1/my/pets", {
      body: {
        clinic_org_id: clinic,
        name: name.trim(),
        species,
        sex,
        date_of_birth: dob || null,
        photo_media_id: photo[0] ?? null,
      },
    });
    setBusy(false);
    if (!data) {
      const parsed = parseApiError(error);
      setErrors(Object.keys(parsed.fields).length ? parsed.fields : { form: parsed.message || tc("tryAgainLater") });
      return;
    }
    router.push(`/app/pets/${data.id}?added=1`);
    router.refresh();
  }

  const summary = Object.entries(errors)
    .filter(([field]) => field !== "form")
    .map(([field, message]) => ({ fieldId: `pet-${field}`, message }));
  const clinicName = clinics.find((c) => c.org_id === clinic)?.name ?? "";
  const sexLabel = { unknown: t("sexUnknown"), female: t("sexFemale"), male: t("sexMale") }[sex];
  return (
    <form onSubmit={submit} noValidate className="space-y-5">
      <StepProgress step={step + 1} total={STEPS.length} title={t(`steps.${STEPS[step]}`)} />
      {summary.length ? <ErrorSummary title={tc("errorSummaryTitle")} errors={summary} /> : null}

      <div className={cn("space-y-5", step !== 0 && "hidden")}>
        <Field id="pet-name" label={t("name")} hint={t("nameHint")} error={errors.name}>
          {(aria) => <TextInput {...aria} value={name} onChange={(e) => setName(e.target.value)} maxLength={80} autoComplete="off" />}
        </Field>
        <RadioGroup
          name="species"
          legend={t("species")}
          inline
          value={species}
          onChange={(v) => setSpecies(v as "dog" | "cat")}
          options={[
            { value: "dog", label: tp("species.dog") },
            { value: "cat", label: tp("species.cat") },
          ]}
        />
        <Field id="pet-sex" label={t("sex")} hint={t("sexHint")}>
          {(aria) => (
            <Select {...aria} value={sex} onChange={(e) => setSex(e.target.value as typeof sex)}>
              <option value="unknown">{t("sexUnknown")}</option>
              <option value="female">{t("sexFemale")}</option>
              <option value="male">{t("sexMale")}</option>
            </Select>
          )}
        </Field>
        <Field id="pet-date_of_birth" label={t("dob")} hint={t("dobHint")} marker={tc("optional")} error={errors.date_of_birth}>
          {(aria) => <TextInput {...aria} type="date" max={today} value={dob} onChange={(e) => setDob(e.target.value)} />}
        </Field>
      </div>

      {/* Kept mounted (only hidden) so an upload in progress is not lost when moving between steps. */}
      <div className={cn("space-y-5", step !== 1 && "hidden")}>
        <Field id="pet-clinic_org_id" label={t("clinic")} hint={t("clinicHint")} error={errors.clinic_org_id}>
          {(aria) => (
            <Select {...aria} value={clinic} onChange={(e) => setClinic(e.target.value)}>
              {clinics.map((c) => (
                <option key={c.org_id} value={c.org_id}>
                  {c.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <fieldset className="space-y-2">
          <legend className="font-display text-sm font-semibold">
            {t("photo")} <span className="font-body font-normal text-ink-2">{tc("optional")}</span>
          </legend>
          <p className="text-sm text-ink-2">{t("photoHint")}</p>
          <Uploader key={clinic} purpose="animal_photo" idPrefix="pet-photo" orgId={clinic} onChange={onPhoto} />
        </fieldset>
      </div>

      {step === 2 ? (
        <div className="space-y-3">
          <p className="text-ink-2">{t("reviewIntro")}</p>
          <ReviewList
            rows={[
              [t("name"), name.trim()],
              [t("species"), tp(`species.${species}`)],
              [t("sex"), sexLabel],
              [t("dob"), dob || tc("notRecorded")],
              [t("clinic"), clinicName],
              [t("photo"), photo.length ? t("photoAdded") : t("photoNone")],
            ]}
          />
        </div>
      ) : null}

      {errors.form ? <p className="font-semibold text-urgent">{errors.form}</p> : null}
      <div className="flex flex-wrap gap-3">
        {step > 0 ? (
          <Button type="button" variant="secondary" size="lg" onClick={() => setStep((s) => s - 1)}>
            {tc("back")}
          </Button>
        ) : null}
        <Button type="submit" size="lg" disabled={busy}>
          {step < STEPS.length - 1 ? tc("continue") : busy ? t("saving") : t("save")}
        </Button>
      </div>
    </form>
  );
}
