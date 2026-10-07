"use client";

import { useTranslations } from "next-intl";
import { useRef, useState } from "react";

import { Button, Notice, cn } from "@pawguard/ui";

import { useRouter } from "@/i18n/navigation";
import { browserApi } from "@/lib/api-browser";

const STATES = ["normal", "not_eating", "unusual_behaviour", "missing", "died", "other"] as const;
type State = (typeof STATES)[number];

/** The owner's one-tap daily update, and the dispute form. Saving refreshes the case (server rendered). */
export function OwnerCheckin({ periodId, day, days, current }: { periodId: string; day: number; days: number; current: State | null }) {
  const t = useTranslations("bite.owner");
  const ts = useTranslations("bite.share.state");
  const router = useRouter();
  const [state, setState] = useState<State | null>(current);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const note = useRef<HTMLInputElement>(null);

  async function save() {
    if (!state) return;
    setBusy(true);
    setError(null);
    const { error: err } = await browserApi.POST("/api/v1/my/bites/{period_id}/checkins", {
      params: { path: { period_id: periodId } },
      body: { state, note: note.current?.value.trim() || null },
    });
    setBusy(false);
    if (err) setError(err.error?.message ?? t("failed"));
    else router.refresh();
  }

  return (
    <fieldset className="space-y-3 rounded-card border border-divider bg-surface p-4" data-testid="owner-checkin">
      <legend className="px-1 font-display text-lg font-semibold">{t("todayTitle", { day, days })}</legend>
      <p className={cn("text-sm", current ? "text-ink-2" : "font-semibold")}>{current ? t("todayDone") : t("todayNeeded")}</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {STATES.map((s) => (
          <label
            key={s}
            className={cn(
              "flex min-h-12 cursor-pointer items-center gap-2 rounded-control border px-3",
              state === s ? "border-primary bg-sage font-semibold" : "border-control bg-surface",
            )}
          >
            <input type="radio" name={`state-${periodId}`} value={s} checked={state === s} onChange={() => setState(s)} />
            {ts(s)}
          </label>
        ))}
      </div>
      <input ref={note} maxLength={300} placeholder={t("notePlaceholder")} aria-label={t("notePlaceholder")} className="w-full rounded-control border border-control bg-surface px-3 py-2" />
      {error ? <Notice tone="urgent">{error}</Notice> : null}
      <Button type="button" onClick={() => void save()} disabled={busy || !state}>
        {busy ? t("saving") : t("save")}
      </Button>
    </fieldset>
  );
}

export function DisputeForm({ periodId }: { periodId: string }) {
  const t = useTranslations("bite.owner");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <details className="rounded-card border border-divider bg-surface p-4">
      <summary className="min-h-11 cursor-pointer content-center font-semibold">{t("disputeTitle")}</summary>
      <form
        className="mt-2 space-y-2"
        onSubmit={async (e) => {
          e.preventDefault();
          const reason = String(new FormData(e.currentTarget).get("reason") ?? "").trim();
          setBusy(true);
          const { error: err } = await browserApi.POST("/api/v1/my/bites/{period_id}/dispute", {
            params: { path: { period_id: periodId } },
            body: { reason },
          });
          setBusy(false);
          if (err) setError(err.error?.message ?? t("failed"));
          else router.refresh();
        }}
      >
        <p className="text-sm text-ink-2">{t("disputeHint")}</p>
        <label className="block space-y-1">
          <span className="block font-semibold">{t("disputeReason")}</span>
          <textarea name="reason" required minLength={10} maxLength={500} rows={3} className="w-full rounded-control border border-control bg-surface p-2" />
        </label>
        {error ? <Notice tone="urgent">{error}</Notice> : null}
        <Button type="submit" variant="secondary" disabled={busy}>
          {t("disputeSend")}
        </Button>
      </form>
    </details>
  );
}

export function VetExamForm({ periodId }: { periodId: string }) {
  const t = useTranslations("bite.clinic");
  const ts = useTranslations("bite.share.state");
  const router = useRouter();
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <details>
      <summary className="min-h-11 cursor-pointer content-center text-sm font-semibold">{t("examTitle")}</summary>
      <form
        className="mt-2 flex flex-wrap items-end gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          setBusy(true);
          const { error } = await browserApi.POST("/api/v1/clinic/bites/{period_id}/exams", {
            params: { path: { period_id: periodId } },
            body: { state: String(f.get("state")) as State, note: String(f.get("note") ?? "").trim() || null },
          });
          setBusy(false);
          setNote(error ? (error.error?.message ?? t("failed")) : t("saved"));
          if (!error) router.refresh();
        }}
      >
        <select name="state" className="min-h-11 rounded-control border border-control bg-surface px-2" aria-label={t("examTitle")}>
          {STATES.map((s) => (
            <option key={s} value={s}>
              {ts(s)}
            </option>
          ))}
        </select>
        <input name="note" maxLength={300} className="min-h-11 rounded-control border border-control bg-surface px-2" aria-label="Note" />
        <Button type="submit" size="sm" disabled={busy}>
          {t("examSave")}
        </Button>
        {note ? <span role="status" className="text-sm">{note}</span> : null}
      </form>
    </details>
  );
}
