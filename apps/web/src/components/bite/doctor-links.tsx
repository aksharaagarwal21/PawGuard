"use client";

import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { Button, Notice } from "@pawguard/ui";

import { useRouter } from "@/i18n/navigation";
import { browserApi } from "@/lib/api-browser";
import { formatDateTime } from "@/lib/format";

type Link = { id: string; expires_at: string; created_at: string; views: number };

/** Reporter only: make a 30-day read-only link for a doctor; see how often links were opened; turn them all off. */
export function DoctorLinks({ token, links, tz }: { token: string; links: Link[]; tz: string }) {
  const t = useTranslations("bite.doctorLinks");
  const locale = useLocale();
  const router = useRouter();
  const [made, setMade] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function make() {
    setBusy(true);
    const { data } = await browserApi.POST("/api/v1/public/bites/{token}/doctor-links", { params: { path: { token } } });
    setBusy(false);
    if (data) {
      setMade(`${window.location.origin}/${locale}${data.path}`);
      router.refresh();
    } else setNote(t("failed"));
  }

  async function revoke() {
    setBusy(true);
    const { data } = await browserApi.POST("/api/v1/public/bites/{token}/doctor-links/revoke", { params: { path: { token } } });
    setBusy(false);
    setMade(null);
    setNote(data ? t("revoked") : t("failed"));
    router.refresh();
  }

  return (
    <section aria-labelledby="doctor-h" className="space-y-3 rounded-card border border-divider bg-surface p-5">
      <h2 id="doctor-h" className="text-xl">
        {t("title")}
      </h2>
      <p className="text-sm text-ink-2">{t("intro")}</p>
      <Button type="button" onClick={() => void make()} disabled={busy}>
        {t("make")}
      </Button>
      {made ? (
        <Notice tone="info">
          <p className="font-semibold">{t("made")}</p>
          <p className="font-mono text-sm break-all" data-testid="doctor-url">
            {made}
          </p>
        </Notice>
      ) : null}
      <p className="text-sm">{t("active", { count: links.length })}</p>
      {links.length ? (
        <ul className="text-sm text-ink-2">
          {links.map((l) => (
            <li key={l.id}>
              {t("until", { date: formatDateTime(l.expires_at, locale, tz) })} · {t("views", { count: l.views })}
            </li>
          ))}
        </ul>
      ) : null}
      {links.length ? (
        <Button type="button" variant="secondary" onClick={() => void revoke()} disabled={busy}>
          {t("revoke")}
        </Button>
      ) : null}
      {note ? <p role="status">{note}</p> : null}
    </section>
  );
}
