"use client";

import { Check, Copy } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useRef, useState } from "react";

import { Button, Notice } from "@pawguard/ui";

import { browserApi } from "@/lib/api-browser";

type Created = { reference: string; tracking_path: string; duplicate: boolean; contact_saved: boolean };

/** Optional bite report: short, no account, no photo. Shows the private tracking link once. */
export function BiteReportForm({ cardToken, today }: { cardToken: string; today: string }) {
  const t = useTranslations("bite.report");
  const tc = useTranslations("bite.created");
  const locale = useLocale();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Created | null>(null);
  const [copied, setCopied] = useState(false);
  const [wantsUpdates, setWantsUpdates] = useState(false);
  const inFlight = useRef(false);

  async function submit(form: HTMLFormElement) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    const f = new FormData(form);
    const email = String(f.get("email") ?? "").trim();
    const { data, error: err } = await browserApi.POST("/api/v1/public/cards/{token}/bites", {
      params: { path: { token: cardToken } },
      body: {
        bite_date: String(f.get("date")),
        bite_time: String(f.get("time") ?? "") || null,
        bitten: f.get("who") === "animal" ? "animal" : "person",
        area: String(f.get("area") ?? "").trim() || null,
        note: String(f.get("note") ?? "").trim() || null,
        contact_email: email && wantsUpdates ? email : null,
        consent_updates: Boolean(email) && wantsUpdates,
        consent_share_with_owner: Boolean(email) && wantsUpdates && f.get("share") === "on",
      },
    });
    setBusy(false);
    inFlight.current = false;
    if (data) setCreated(data);
    else setError(err?.error?.message ?? t("failed"));
  }

  if (created) {
    const url = `${window.location.origin}/${locale}${created.tracking_path}`;
    return (
      <section aria-labelledby="created-h" className="space-y-3 rounded-card border-2 border-primary bg-sage p-5" data-testid="bite-created">
        <h2 id="created-h" className="text-xl">
          {tc("title", { reference: created.reference })}
        </h2>
        <p className="font-semibold">{tc("save")}</p>
        <p className="font-mono text-sm break-all" data-testid="tracking-url">
          {url}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              void navigator.clipboard?.writeText(url).then(() => setCopied(true));
            }}
          >
            {copied ? <Check aria-hidden className="size-4" /> : <Copy aria-hidden className="size-4" />}
            {copied ? tc("copied") : tc("copy")}
          </Button>
          <Button asChild>
            <a href={url}>{tc("open")}</a>
          </Button>
        </div>
        {created.duplicate ? <p className="text-sm">{tc("duplicate")}</p> : null}
        {created.contact_saved ? <p className="text-sm">{tc("emailed")}</p> : null}
      </section>
    );
  }

  const field = "w-full rounded-control border border-control bg-surface px-3 py-2";
  return (
    <section aria-labelledby="report-h" className="space-y-3 rounded-card border border-divider bg-surface p-5">
      <h2 id="report-h" className="text-xl">
        {t("title")}
      </h2>
      <p className="text-sm text-ink-2">{t("intro")}</p>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          void submit(e.currentTarget);
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1">
            <span className="block font-semibold">{t("when")}</span>
            <input name="date" type="date" required max={today} defaultValue={today} className={field} />
          </label>
          <label className="space-y-1">
            <span className="block font-semibold">{t("time")}</span>
            <input name="time" type="time" className={field} />
          </label>
        </div>
        <fieldset className="space-y-1">
          <legend className="font-semibold">{t("who")}</legend>
          <label className="mr-4 inline-flex min-h-11 items-center gap-2">
            <input type="radio" name="who" value="person" defaultChecked /> {t("person")}
          </label>
          <label className="inline-flex min-h-11 items-center gap-2">
            <input type="radio" name="who" value="animal" /> {t("animal")}
          </label>
        </fieldset>
        <label className="block space-y-1">
          <span className="block font-semibold">{t("area")}</span>
          <input name="area" maxLength={80} className={field} />
        </label>
        <label className="block space-y-1">
          <span className="block font-semibold">{t("note")}</span>
          <textarea name="note" maxLength={500} rows={2} className={field} />
        </label>
        <label className="flex min-h-11 items-center gap-2">
          <input type="checkbox" checked={wantsUpdates} onChange={(e) => setWantsUpdates(e.target.checked)} /> {t("consent")}
        </label>
        {wantsUpdates ? (
          <div className="space-y-2 border-l-4 border-divider pl-3">
            <label className="block space-y-1">
              <span className="block font-semibold">{t("email")}</span>
              <input name="email" type="email" autoComplete="email" maxLength={254} className={field} />
            </label>
            <label className="flex min-h-11 items-center gap-2">
              <input type="checkbox" name="share" /> {t("share")}
            </label>
          </div>
        ) : null}
        <p className="text-sm text-ink-2">{t("doctorLater")}</p>
        {error ? <Notice tone="urgent">{error}</Notice> : null}
        <Button type="submit" disabled={busy} size="lg">
          {busy ? t("sending") : t("submit")}
        </Button>
      </form>
    </section>
  );
}
