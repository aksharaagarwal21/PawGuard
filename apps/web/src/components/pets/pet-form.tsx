"use client";

import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";

import { Button, ErrorSummary, Field, RadioGroup, Select, TextInput } from "@pawguard/ui";

import { Uploader } from "@/components/prevention/uploader";
import { useRouter } from "@/i18n/navigation";
import { browserApi, parseApiError, type FieldErrors } from "@/lib/api-browser";

type Clinic = { org_id: string; name: string };

export function PetForm({ clinics, today }: { clinics: Clinic[]; today: string }) {
  const t = useTranslations("pets.form");
  const tp = useTranslations("pets");
  const tc = useTranslations("common");
  const router = useRouter();
  const [clinic, setClinic] = useState(clinics[0]?.org_id ?? "");
  const [name, setName] = useState("");
  const [species, setSpecies] = useState<"dog" | "cat">("dog");
  const [sex, setSex] = useState<"female" | "male" | "unknown">("unknown");
  const [dob, setDob] = useState("");
  const [photo, setPhoto] = useState<string[]>([]);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);
  const onPhoto = useCallback((ids: string[]) => setPhoto(ids), []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const local: FieldErrors = {};
    if (!name.trim()) local.name = t("nameRequired");
    if (!clinic) local.clinic_org_id = t("clinicRequired");
    if (dob && dob > today) local.date_of_birth = t("dobFuture");
    setErrors(local);
    if (Object.keys(local).length) return;
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
    router.push(`/app/pets/${data.id}`);
    router.refresh();
  }

  const summary = Object.entries(errors)
    .filter(([field]) => field !== "form")
    .map(([field, message]) => ({ fieldId: `pet-${field}`, message }));
  return (
    <form onSubmit={submit} noValidate className="space-y-5">
      {summary.length ? <ErrorSummary title={tc("errorSummaryTitle")} errors={summary} /> : null}
      <Field id="pet-name" label={t("name")} error={errors.name}>
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
      <Field id="pet-sex" label={t("sex")}>
        {(aria) => (
          <Select {...aria} value={sex} onChange={(e) => setSex(e.target.value as typeof sex)}>
            <option value="unknown">{t("sexUnknown")}</option>
            <option value="female">{t("sexFemale")}</option>
            <option value="male">{t("sexMale")}</option>
          </Select>
        )}
      </Field>
      <Field id="pet-date_of_birth" label={t("dob")} marker={tc("optional")} error={errors.date_of_birth}>
        {(aria) => <TextInput {...aria} type="date" max={today} value={dob} onChange={(e) => setDob(e.target.value)} />}
      </Field>
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
        <Uploader key={clinic} purpose="animal_photo" idPrefix="pet-photo" orgId={clinic} onChange={onPhoto} />
      </fieldset>
      {errors.form ? <p className="font-semibold text-urgent">{errors.form}</p> : null}
      <Button type="submit" size="lg" disabled={busy}>
        {busy ? t("saving") : t("save")}
      </Button>
    </form>
  );
}
