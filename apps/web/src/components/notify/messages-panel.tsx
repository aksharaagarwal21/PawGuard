"use client";

import type { Schemas } from "@pawguard/api-client";
import { AlertTriangle, CheckCircle2, CircleDashed, Clock } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { Button, cn } from "@pawguard/ui";

import { useRouter } from "@/i18n/navigation";
import { browserApi } from "@/lib/api-browser";
import { formatDateTime } from "@/lib/format";

type Overview = Schemas["NotificationsOverviewOut"];

const STATE_ICON = { ok: CheckCircle2, not_configured: CircleDashed } as const;

/** Clinic staff: is each channel working, and what was sent recently (states only, never addresses). */
export function MessagesPanel({ data, tz, demo }: { data: Overview; tz: string; demo: boolean }) {
  const t = useTranslations("notify.panel");
  const locale = useLocale();
  const router = useRouter();
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function runNow() {
    setBusy(true);
    const { data: res } = await browserApi.POST("/api/v1/clinic/notifications/run");
    setBusy(false);
    setNote(res ? t("queued", { count: res.queued }) : t("failed"));
    router.refresh();
  }

  return (
    <section aria-labelledby="messages-h" className="space-y-3 rounded-card border border-divider bg-surface p-4">
      <h2 id="messages-h" className="text-lg">{t("title")}</h2>
      <ul className="grid gap-2 sm:grid-cols-3">
        {data.providers.map((p) => {
          const Icon = p.state === "ok" ? STATE_ICON.ok : p.state === "not_configured" ? STATE_ICON.not_configured : AlertTriangle;
          return (
            <li key={p.provider} className={cn("rounded-control border p-3", p.state === "ok" ? "border-divider" : p.state === "not_configured" ? "border-control" : "border-urgent")}>
              <p className="flex items-center gap-1.5 font-display font-semibold">
                <Icon aria-hidden className={cn("size-4", p.state === "ok" ? "text-primary" : p.state === "not_configured" ? "text-ink-2" : "text-urgent")} />
                {t(`provider.${p.provider}`)}
              </p>
              <p className="text-sm">{p.state === "ok" && !p.updated_at ? t("state.ready") : t(`state.${p.state}`)}</p>
              {p.detail && p.state !== "ok" ? <p className="text-xs text-ink-2">{p.detail}</p> : null}
            </li>
          );
        })}
      </ul>
      {data.deliveries.length === 0 ? (
        <p className="text-sm text-ink-2">{t("none")}</p>
      ) : (
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-labelledby="messages-h">
          <table className="w-full min-w-[32rem] text-left text-sm">
            <thead>
              <tr className="border-b border-divider">
                <th scope="col" className="py-2 pr-3">{t("colWhen")}</th>
                <th scope="col" className="py-2 pr-3">{t("colChannel")}</th>
                <th scope="col" className="py-2 pr-3">{t("colAbout")}</th>
                <th scope="col" className="py-2">{t("colState")}</th>
              </tr>
            </thead>
            <tbody>
              {data.deliveries.map((d) => (
                <tr key={d.id} className="border-b border-divider last:border-0">
                  <td className="py-2 pr-3">{formatDateTime(d.sent_at ?? d.created_at, locale, tz)}</td>
                  <td className="py-2 pr-3">{t(`provider.${d.channel}`)}</td>
                  <td className="py-2 pr-3">{d.kind === "test" ? t("test") : d.kind === "verify_email" ? t("verify") : d.kind === "lost_message" ? t("lostMessage") : (d.pet_name ?? "—")}</td>
                  <td className="py-2">
                    <span className="inline-flex items-center gap-1">
                      {d.state === "sent" ? <CheckCircle2 aria-hidden className="size-3.5 text-primary" /> : d.state === "failed" ? <AlertTriangle aria-hidden className="size-3.5 text-urgent" /> : <Clock aria-hidden className="size-3.5 text-ink-2" />}
                      {t(`delivery.${d.state}`)}
                    </span>
                    {d.reply ? <span className="block text-xs text-ink-2">{t(`reply.${d.reply}`)}</span> : null}
                    {d.last_error && d.state !== "sent" ? <span className="block text-xs text-ink-2">{d.last_error}</span> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.whatsapp_webhook_url ? (
        <p className="text-sm text-ink-2">
          {t("webhook")} <code className="break-all rounded bg-canvas px-1.5 py-0.5 text-ink">{data.whatsapp_webhook_url}</code>
        </p>
      ) : null}
      {demo ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={runNow}>
            {t("runNow")}
          </Button>
          <span className="text-sm text-ink-2">{note ?? t("runHint")}</span>
        </div>
      ) : null}
    </section>
  );
}
