"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button, Field, Select, TextInput } from "@pawguard/ui";

import { useRouter } from "@/i18n/navigation";
import { browserApi, parseApiError } from "@/lib/api-browser";

export function NewCampaign({ areas }: { areas: { id: string; name: string }[] }) {
  const t = useTranslations("campaigns");
  const tc = useTranslations("common");
  const router = useRouter();
  const [name, setName] = useState("");
  const [activity, setActivity] = useState<"vaccination" | "survey">("vaccination");
  const [chosen, setChosen] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create() {
    if (name.trim().length < 3 || chosen.length === 0) {
      setError(t("needNameAndAreas"));
      return;
    }
    setBusy(true);
    const { data, error: apiError } = await browserApi.POST("/api/v1/campaigns", {
      body: { name: name.trim(), activity, area_ids: chosen },
    });
    setBusy(false);
    if (data) router.push(`/app/campaigns/${data.id}`);
    else setError(parseApiError(apiError).message || tc("tryAgainLater"));
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg">{t("newTitle")}</h2>
      <Field id="campaign-name" label={t("name")}>
        {(aria) => <TextInput {...aria} value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />}
      </Field>
      <Field id="campaign-activity" label={t("activityLabel")}>
        {(aria) => (
          <Select {...aria} value={activity} onChange={(e) => setActivity(e.target.value as typeof activity)}>
            <option value="vaccination">{t("activity.vaccination")}</option>
            <option value="survey">{t("activity.survey")}</option>
          </Select>
        )}
      </Field>
      <fieldset className="space-y-1">
        <legend className="font-semibold">{t("areas")}</legend>
        {areas.map((a) => (
          <label key={a.id} className="flex min-h-11 items-center gap-2">
            <input
              type="checkbox"
              className="size-5 accent-primary"
              checked={chosen.includes(a.id)}
              onChange={(e) => setChosen((c) => (e.target.checked ? [...c, a.id] : c.filter((x) => x !== a.id)))}
            />
            {a.name}
          </label>
        ))}
      </fieldset>
      {error ? (
        <p role="alert" className="font-semibold text-urgent">
          {error}
        </p>
      ) : null}
      <Button onClick={create} loading={busy}>
        {t("create")}
      </Button>
    </div>
  );
}
