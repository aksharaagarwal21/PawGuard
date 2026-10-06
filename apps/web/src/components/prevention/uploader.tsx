"use client";

import { Camera, FileUp, Loader2, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { browserApi } from "@/lib/api-browser";

import { SubjectPicker, type SubjectChoice } from "./subject-picker";

const MAX_BYTES = 15 * 1024 * 1024;
const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

export type UploadedMedia = { id: string; state: string; thumbUrl?: string; name: string };
type Item = UploadedMedia & { progress: number; phase: "uploading" | "checking" | "ready" | "pending" | "rejected" | "failed"; reason?: string; xhr?: XMLHttpRequest };

/**
 * Upload flow: client-side type/size check → upload intent (API) → PUT bytes to the single-object signed URL
 * (progress) → complete (API) → poll validation. A file that is "uploaded" but not yet checked can already be
 * attached (the worker validates it shortly); rejected files show a plain reason and can be removed.
 */
export function Uploader({
  purpose,
  multiple = false,
  allowPdf = false,
  onChange,
  onSubjects,
  subjectPurpose = "record",
  idPrefix,
  orgId,
}: {
  purpose: "animal_photo" | "vaccination_evidence";
  multiple?: boolean;
  allowPdf?: boolean;
  onChange: (ids: string[]) => void;
  /** Animal photos only: which detected dog each photo is about, plus quality warnings and override reason. */
  onSubjects?: (choices: SubjectChoice[]) => void;
  subjectPurpose?: "record" | "lookup";
  idPrefix: string;
  /** Upload into this organisation instead of the active one (the API checks membership). */
  orgId?: string;
}) {
  const orgHeaders = useMemo(() => (orgId ? { "x-pawguard-org": orgId } : undefined), [orgId]);
  const t = useTranslations("upload");
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [subjects, setSubjects] = useState<Record<string, SubjectChoice>>({});
  const onSubject = useCallback((c: SubjectChoice) => setSubjects((prev) => ({ ...prev, [c.mediaId]: c })), []);
  useEffect(() => {
    const live = new Set(items.map((i) => i.id));
    onSubjects?.(Object.values(subjects).filter((s) => live.has(s.mediaId)));
  }, [subjects, items, onSubjects]);
  const cameraRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const types = allowPdf ? [...IMAGE_TYPES, "application/pdf"] : IMAGE_TYPES;

  useEffect(() => {
    onChange(items.filter((i) => ["ready", "pending", "checking"].includes(i.phase)).map((i) => i.id));
  }, [items, onChange]);

  const patch = useCallback((id: string, p: Partial<Item>) => {
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, ...p } : i)));
  }, []);

  const poll = useCallback(
    async (id: string) => {
      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, i < 5 ? 800 : 2000));
        const { data } = await browserApi.GET("/api/v1/media/{media_id}", {
          params: { path: { media_id: id } },
          headers: orgHeaders,
        });
        if (!data) continue;
        if (data.state === "approved") {
          const { data: link } = await browserApi.GET("/api/v1/media/{media_id}/url", {
            params: { path: { media_id: id }, query: { variant: "thumb" } },
            headers: orgHeaders,
          });
          patch(id, { phase: "ready", state: "approved", thumbUrl: link?.url });
          return;
        }
        if (data.state === "rejected") {
          patch(id, { phase: "rejected", state: "rejected", reason: data.rejection_code ?? "other" });
          return;
        }
      }
      patch(id, { phase: "pending" }); // worker busy or offline: keep the file, validation will follow
    },
    [patch, orgHeaders],
  );

  async function upload(file: File) {
    setError(null);
    if (!types.includes(file.type)) return setError(t("wrongType"));
    if (file.size > MAX_BYTES) return setError(t("tooLarge"));
    const { data: intent, error: apiError } = await browserApi.POST("/api/v1/media/upload-intents", {
      body: { purpose, content_type: file.type as "image/jpeg", byte_size: file.size },
      headers: orgHeaders,
    });
    if (!intent) return setError(apiError?.error?.message ?? t("failed"));
    const item: Item = { id: intent.media_id, state: "pending_upload", name: file.name, progress: 0, phase: "uploading" };
    setItems((prev) => (multiple ? [...prev, item] : [item]));
    const xhr = new XMLHttpRequest();
    patch(item.id, { xhr });
    const ok = await new Promise<boolean>((resolve) => {
      xhr.open("PUT", intent.upload_url);
      for (const [k, v] of Object.entries(intent.headers)) xhr.setRequestHeader(k, v);
      xhr.upload.onprogress = (e) => e.lengthComputable && patch(item.id, { progress: Math.round((e.loaded / e.total) * 100) });
      xhr.onload = () => resolve(xhr.status >= 200 && xhr.status < 300);
      xhr.onerror = () => resolve(false);
      xhr.onabort = () => resolve(false);
      xhr.send(file);
    });
    if (!ok) {
      patch(item.id, { phase: "failed" });
      return;
    }
    const { data: done } = await browserApi.POST("/api/v1/media/{media_id}/complete", {
      params: { path: { media_id: item.id } },
      headers: orgHeaders,
    });
    if (!done || done.state === "rejected") {
      patch(item.id, { phase: "rejected", reason: done?.rejection_code ?? "other" });
      return;
    }
    patch(item.id, { phase: "checking", state: done.state });
    void poll(item.id);
  }

  async function remove(item: Item) {
    item.xhr?.abort();
    setItems((prev) => prev.filter((i) => i.id !== item.id));
    await browserApi.DELETE("/api/v1/media/{media_id}", { params: { path: { media_id: item.id } }, headers: orgHeaders });
  }

  const accept = types.join(",");
  const canAdd = multiple || items.length === 0;
  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-2">{t("purpose")}</p>
      {canAdd ? (
        <div className="flex flex-wrap gap-2">
          {purpose === "animal_photo" ? (
            <button type="button" onClick={() => cameraRef.current?.click()} className="inline-flex min-h-11 items-center gap-2 rounded-control border border-control bg-surface px-4 font-display text-sm font-semibold hover:bg-sage">
              <Camera aria-hidden className="size-4" />
              {t("takePhoto")}
            </button>
          ) : null}
          <button type="button" onClick={() => fileRef.current?.click()} className="inline-flex min-h-11 items-center gap-2 rounded-control border border-control bg-surface px-4 font-display text-sm font-semibold hover:bg-sage">
            <FileUp aria-hidden className="size-4" />
            {purpose === "animal_photo" ? t("choosePhoto") : t("chooseFile")}
          </button>
          <input ref={cameraRef} id={`${idPrefix}-camera`} type="file" accept="image/*" capture="environment" className="sr-only" tabIndex={-1} aria-label={t("takePhoto")} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0]).finally(() => (e.target.value = ""))} />
          <input ref={fileRef} id={`${idPrefix}-file`} type="file" accept={accept} className="sr-only" tabIndex={-1} aria-label={purpose === "animal_photo" ? t("choosePhoto") : t("chooseFile")} data-testid={`${idPrefix}-file-input`} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0]).finally(() => (e.target.value = ""))} />
        </div>
      ) : null}
      <p className="text-xs text-ink-2">{allowPdf ? t("constraintsEvidence") : t("constraintsImage")}</p>
      {error ? (
        <p role="alert" className="text-sm font-semibold text-urgent">
          {error}
        </p>
      ) : null}
      <ul className="space-y-2" aria-live="polite">
        {items.map((i) => (
          <li key={i.id} className="flex flex-wrap items-center gap-3 rounded-control border border-divider bg-surface p-2">
            {i.thumbUrl ? (
              // eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL
              <img src={i.thumbUrl} alt={t("thumbAlt")} className="size-12 rounded-md object-cover" />
            ) : (
              <span className="flex size-12 items-center justify-center rounded-md bg-sage">
                {i.phase === "uploading" || i.phase === "checking" ? <Loader2 aria-hidden className="size-5 animate-spin text-primary" /> : <FileUp aria-hidden className="size-5 text-primary" />}
              </span>
            )}
            <div className="min-w-0 flex-1 text-sm">
              <p className="truncate font-semibold">{i.name}</p>
              <p className={i.phase === "rejected" || i.phase === "failed" ? "font-semibold text-urgent" : "text-ink-2"}>
                {i.phase === "uploading"
                  ? t("uploading", { percent: i.progress })
                  : i.phase === "checking"
                    ? t("checking")
                    : i.phase === "ready"
                      ? t("ready")
                      : i.phase === "pending"
                        ? t("pending")
                        : i.phase === "failed"
                          ? t("failed")
                          : t("rejected", { reason: t.has(`reasons.${i.reason}`) ? t(`reasons.${i.reason}`) : t("reasons.other") })}
              </p>
            </div>
            <button type="button" onClick={() => remove(i)} className="inline-flex size-11 items-center justify-center rounded-md hover:bg-sage" aria-label={`${t("remove")}: ${i.name}`}>
              <X aria-hidden className="size-4" />
            </button>
            {purpose === "animal_photo" && i.phase === "ready" ? (
              <div className="basis-full pt-2">
                <SubjectPicker mediaId={i.id} onChange={onSubject} purpose={subjectPurpose} />
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
