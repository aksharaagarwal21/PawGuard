"use client";

import type { Schemas } from "@pawguard/api-client";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Field, Notice, RadioGroup, Textarea } from "@pawguard/ui";

import { browserApi } from "@/lib/api-browser";

type Analysis = Schemas["MediaAnalysisOut"];
export type SubjectChoice = {
  mediaId: string;
  source: "detector" | "none";
  box: { x: number; y: number; w: number; h: number } | null;
  dogCount: number | null;
  warnings: string[];
  overrideReason: string;
};

/**
 * Shows where the detector *may* have found dogs (numbered boxes) and asks which one the record is about.
 * Boxes are drawn from returned pixel coordinates in an SVG whose viewBox is the original image size, so the
 * displayed overlay and stored coordinates always agree. The numbered radio list is the accessible equivalent of
 * the drawing. Nothing is preselected when there are several dogs.
 */
export function SubjectPicker({
  mediaId,
  onChange,
  purpose = "record",
}: {
  mediaId: string;
  onChange: (c: SubjectChoice) => void;
  /** "lookup": the person is asking which registered animal this is, not adding to a known record. */
  purpose?: "record" | "lookup";
}) {
  const t = useTranslations("subject");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [imgUrl, setImgUrl] = useState<string | null>(null);
  const [choice, setChoice] = useState<string>("");
  const [reason, setReason] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      for (let i = 0; i < 30 && !cancelled; i++) {
        const { data } = await browserApi.GET("/api/v1/media/{media_id}/analysis", { params: { path: { media_id: mediaId } } });
        if (data && data.state !== "pending") {
          setAnalysis(data);
          if (data.dogs.length === 1) setChoice("0");
          const { data: link } = await browserApi.GET("/api/v1/media/{media_id}/url", {
            params: { path: { media_id: mediaId }, query: { variant: "display" } },
          });
          if (!cancelled) setImgUrl(link?.url ?? null);
          return;
        }
        await new Promise((r) => setTimeout(r, i < 5 ? 1000 : 2500));
      }
      if (!cancelled) setAnalysis({ state: "unavailable" } as Analysis);
    })();
    return () => {
      cancelled = true;
    };
  }, [mediaId]);

  const warnings = Array.from(new Set((analysis?.quality ?? []).flatMap((q) => q.warnings)));
  useEffect(() => {
    if (!analysis) return;
    const idx = choice === "" || choice === "none" ? -1 : Number(choice);
    const box = idx >= 0 ? analysis.dogs[idx] : undefined;
    onChange({
      mediaId,
      source: box ? "detector" : "none",
      box: box ? { x: box.x, y: box.y, w: box.w, h: box.h } : null,
      dogCount: analysis.state === "completed" || analysis.state === "no_animal" ? analysis.dogs.length : null,
      warnings,
      overrideReason: reason,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- warnings derives from analysis
  }, [analysis, choice, reason, mediaId, onChange]);

  if (!analysis) {
    return (
      <p role="status" className="text-sm text-ink-2">
        {t("checking")}
      </p>
    );
  }
  const w = analysis.image_width ?? 1;
  const h = analysis.image_height ?? 1;
  return (
    <div className="space-y-3">
      {imgUrl && analysis.dogs.length > 0 ? (
        <div className="relative w-full max-w-lg">
          {/* eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL */}
          <img src={imgUrl} alt={t("photoAlt")} className="block h-auto w-full rounded-md" />
          <svg aria-hidden viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
            {analysis.dogs.map((d, i) => {
              const selected = choice === String(i);
              return (
                <g key={i}>
                  <rect x={d.x} y={d.y} width={d.w} height={d.h} fill="none" stroke={selected ? "#205C4F" : "#FFFFFF"} strokeWidth={Math.max(3, w / 200)} />
                  <rect x={d.x} y={d.y} width={Math.max(28, w / 20)} height={Math.max(28, w / 20)} fill={selected ? "#205C4F" : "#203A34"} />
                  <text x={d.x + Math.max(14, w / 40)} y={d.y + Math.max(20, w / 28)} fill="#FFFFFF" fontSize={Math.max(18, w / 30)} textAnchor="middle" fontFamily="sans-serif">
                    {i + 1}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      ) : null}

      {analysis.state === "completed" && analysis.dogs.length > 0 ? (
        <RadioGroup
          name={`subject-${mediaId}`}
          legend={purpose === "lookup" ? t("whichDogLookup") : analysis.dogs.length > 1 ? t("whichDog") : t("isThisTheDog")}
          value={choice}
          onChange={setChoice}
          options={[
            ...analysis.dogs.map((_, i) => ({ value: String(i), label: t("dogNumber", { n: i + 1 }) })),
            { value: "none", label: t("noneOfThese"), hint: t("noneOfTheseHint") },
          ]}
        />
      ) : null}
      {analysis.state === "no_animal" ? <Notice tone="info">{t("noDogFound")}</Notice> : null}
      {analysis.state === "unavailable" || analysis.state === "failed" ? <Notice tone="info">{t("detectionUnavailable")}</Notice> : null}
      {analysis.person_count > 0 ? <Notice tone="pending" title={t("personTitle")}>{t("personBody")}</Notice> : null}
      <p className="text-xs text-ink-2">{t("detectionOnly")}</p>

      {warnings.length ? (
        <div className="space-y-2 rounded-card bg-sand p-3">
          <p className="font-display text-sm font-semibold">{t("qualityTitle")}</p>
          <ul className="list-disc pl-5 text-sm">
            {warnings.map((wn) => (
              <li key={wn}>{t.has(`warnings.${wn}`) ? t(`warnings.${wn}`) : wn}</li>
            ))}
          </ul>
          <Field id={`override-${mediaId}`} label={t("overrideLabel")} hint={t("overrideHint")}>
            {(aria) => <Textarea {...aria} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />}
          </Field>
        </div>
      ) : null}
    </div>
  );
}
