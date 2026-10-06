"use client";

import { useTranslations } from "next-intl";
import { useCallback, useRef, useState } from "react";

import { Button, Card, Field, Select, TextInput, Textarea } from "@pawguard/ui";

import { LocationInput, type CapturedLocation } from "@/components/prevention/location-input";
import type { SubjectChoice } from "@/components/prevention/subject-picker";
import { Uploader } from "@/components/prevention/uploader";
import { useRouter } from "@/i18n/navigation";
import { browserApi, newKey, parseApiError } from "@/lib/api-browser";
import { todayIso } from "@/lib/format";

export function SightingForm({
  animalId,
  defaultArea,
  areas,
  canUpload,
}: {
  animalId: string;
  defaultArea: string;
  areas: { id: string; name: string }[];
  canUpload: boolean;
}) {
  const t = useTranslations("capture");
  const tf = useTranslations("animalForm");
  const tc = useTranslations("common");
  const router = useRouter();
  const [area, setArea] = useState(defaultArea);
  const [date, setDate] = useState(todayIso());
  const [notes, setNotes] = useState("");
  const [location, setLocation] = useState<CapturedLocation | null>(null);
  const [media, setMedia] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const op = useRef(newKey());
  const onMedia = useCallback((ids: string[]) => setMedia(ids), []);
  const [subjects, setSubjects] = useState<SubjectChoice[]>([]);
  const onSubjects = useCallback((c: SubjectChoice[]) => setSubjects(c), []);

  async function save() {
    if (subjects.some((s) => s.warnings.length && s.overrideReason.trim().length < 3)) {
      setError(tc("reasonRequired"));
      return;
    }
    setBusy(true);
    setError(null);
    const { data, error: apiError } = await browserApi.POST("/api/v1/observations", {
      headers: { "Idempotency-Key": op.current },
      body: {
        animal_id: animalId,
        observed_on: date || null,
        time_precision: date ? "day" : "unknown",
        area_id: area || null,
        location,
        notes: notes.trim() || null,
        media_ids: media,
        subjects: subjects.map((s) => ({ media_id: s.mediaId, source: s.source, box: s.box, dog_count: s.dogCount })),
        quality_override_reason: subjects.map((s) => s.overrideReason.trim()).filter(Boolean).join("; ") || null,
        client_operation_id: op.current,
      },
    });
    setBusy(false);
    if (data) {
      router.push(`/app/animals/${animalId}?tab=sightings`);
      router.refresh();
      return;
    }
    const p = parseApiError(apiError);
    setError(Object.values(p.fields)[0] ?? p.message ?? tc("tryAgainLater"));
  }

  return (
    <div className="space-y-5">
      <Card className="space-y-5">
        <Field id="observed_on" label={tf("when")}>
          {(aria) => <TextInput {...aria} type="date" max={todayIso()} value={date} onChange={(e) => setDate(e.target.value)} />}
        </Field>
        <Field id="area_id" label={tf("area")}>
          {(aria) => (
            <Select {...aria} value={area} onChange={(e) => setArea(e.target.value)}>
              <option value="">{tf("noArea")}</option>
              {areas.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </Select>
          )}
        </Field>
        <LocationInput value={location} onChange={setLocation} />
        <Field id="notes" label={t("notes")} hint={t("notesHint")} marker={tc("optional")}>
          {(aria) => <Textarea {...aria} maxLength={1000} value={notes} onChange={(e) => setNotes(e.target.value)} />}
        </Field>
      </Card>
      {canUpload ? (
        <Card className="space-y-2">
          <h2 className="text-base">{tf("photoOptional")}</h2>
          <Uploader purpose="animal_photo" onChange={onMedia} onSubjects={onSubjects} idPrefix="sighting-photo" />
        </Card>
      ) : null}
      {error ? (
        <p role="alert" className="font-semibold text-urgent">
          {error}
        </p>
      ) : null}
      <div className="flex justify-end">
        <Button onClick={save} loading={busy} size="lg">
          {t("saveSighting")}
        </Button>
      </div>
    </div>
  );
}
