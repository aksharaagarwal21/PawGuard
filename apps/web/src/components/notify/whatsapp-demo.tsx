"use client";

import type { Schemas } from "@pawguard/api-client";
import { AlertTriangle, CheckCheck, CheckCircle2, CircleDashed, Clock, MessageCircle } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button, Notice, StatusChip, cn } from "@pawguard/ui";

import { browserApi } from "@/lib/api-browser";
import { formatDateTime } from "@/lib/format";

type Demo = Schemas["WhatsAppDemoOut"];
type Item = Demo["history"][number];

/** Demo times are always shown in India Standard Time, whatever the browser's zone. */
const IST = "Asia/Kolkata";
const FINAL = new Set(["delivered", "read", "undelivered", "failed", "canceled"]);

function waiting(i: Item): boolean {
  if (i.state === "queued" || i.state === "sending" || i.state === "deferred") return true;
  return i.state === "sent" && !(i.provider_status && FINAL.has(i.provider_status));
}

/** One status per row, keeping "accepted by Twilio", "sent", "delivered", "read" and "failed" distinct. */
function statusKey(i: Item, now: number): string {
  if (i.state === "queued") return Date.parse(i.scheduled_for) > now ? "scheduled" : "waiting";
  if (i.state === "failed" && (i.provider_status === "undelivered" || i.provider_status === "failed"))
    return `twilio_${i.provider_status}`; // reported by Twilio after it accepted the message
  if (i.state !== "sent") return i.state;
  switch (i.provider_status) {
    case "delivered":
    case "read":
    case "undelivered":
    case "failed":
    case "sent":
    case "sending":
      return `twilio_${i.provider_status}`;
    default:
      return "twilio_accepted";
  }
}

function StatusIcon({ k }: { k: string }) {
  if (k === "twilio_read") return <CheckCheck aria-hidden className="size-3.5 text-primary" />;
  if (k === "twilio_delivered") return <CheckCircle2 aria-hidden className="size-3.5 text-primary" />;
  if (k === "failed" || k === "twilio_failed" || k === "twilio_undelivered")
    return <AlertTriangle aria-hidden className="size-3.5 text-urgent" />;
  if (k === "skipped") return <CircleDashed aria-hidden className="size-3.5 text-ink-2" />;
  return <Clock aria-hidden className="size-3.5 text-ink-2" />;
}

/** Clinic demo tools: send the Twilio trial WhatsApp template to the one configured demo recipient, now or in two
 * minutes (sent by the server, so this tab can be closed), and follow its delivery. No pet records change. */
export function WhatsAppDemo() {
  const t = useTranslations("notify.waDemo");
  const locale = useLocale();
  const [d, setD] = useState<Demo | null>(null);
  const [hidden, setHidden] = useState(false);
  const [busy, setBusy] = useState<"test" | "schedule" | null>(null);
  const [note, setNote] = useState<{ tone: "info" | "urgent"; text: string } | null>(null);
  const [now, setNow] = useState(0);
  const inFlight = useRef(false);

  const reload = useCallback(async () => {
    const { data, response } = await browserApi.GET("/api/v1/clinic/whatsapp-demo");
    if (data) setD(data);
    else if (response.status === 403) setHidden(true);
    setNow(Date.now());
  }, []);

  useEffect(() => {
    const id = window.setTimeout(() => void reload(), 0);
    return () => window.clearTimeout(id);
  }, [reload]);

  // Follow delivery while something is still on its way (bounded: only items from the last 30 minutes).
  useEffect(() => {
    if (!d) return;
    const live = d.history.some((i) => waiting(i) && Date.now() - Date.parse(i.created_at) < 30 * 60_000);
    if (!live) return;
    const id = window.setTimeout(() => void reload(), 5000);
    return () => window.clearTimeout(id);
  }, [d, reload]);

  async function send(kind: "test" | "schedule") {
    if (inFlight.current) return; // double-click protection (the server refuses duplicates too)
    inFlight.current = true;
    setBusy(kind);
    setNote(null);
    const { data, error } = await browserApi.POST(
      kind === "test" ? "/api/v1/clinic/whatsapp-demo/test" : "/api/v1/clinic/whatsapp-demo/schedule",
    );
    if (data) {
      setNote({
        tone: "info",
        text: kind === "test" ? t("queuedNow") : t("scheduledFor", { time: formatDateTime(data.scheduled_for, locale, IST) }),
      });
    } else {
      setNote({ tone: "urgent", text: error?.error?.message ?? t("failed") });
    }
    await reload();
    setBusy(null);
    inFlight.current = false;
  }

  async function cancel(id: string) {
    const { error } = await browserApi.POST("/api/v1/clinic/whatsapp-demo/{delivery_id}/cancel", {
      params: { path: { delivery_id: id } },
    });
    setNote(error ? { tone: "urgent", text: error.error?.message ?? t("failed") } : { tone: "info", text: t("cancelled") });
    await reload();
  }

  if (hidden || !d) return null;
  const preview = d.template_body ?? d.template_sample;

  return (
    <section aria-labelledby="wa-demo-h" className="space-y-3 rounded-card border border-divider bg-surface p-4" data-testid="whatsapp-demo">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="wa-demo-h" className="flex items-center gap-2 text-base">
          <MessageCircle aria-hidden className="size-5 text-ink-2" />
          {t("title")}
        </h3>
        {d.ready ? <StatusChip kind="verified">{t("ready")}</StatusChip> : <StatusChip kind="draft">{t("notReady")}</StatusChip>}
      </div>

      {d.missing.length > 0 ? (
        <Notice tone="pending">
          <p>{t("missingIntro")}</p>
          <ul className="mt-1 list-disc pl-5">
            {d.missing.map((m) => (
              <li key={m}>
                <code className="break-all">{m}</code>
              </li>
            ))}
          </ul>
          <p className="mt-1 text-sm">{t("missingHint")}</p>
        </Notice>
      ) : null}

      <p className="text-sm">
        {t("recipient")} <strong>{d.recipient_masked}</strong> <span className="text-ink-2">{t("recipientNote")}</span>
      </p>

      <figure className="space-y-1">
        <figcaption className="text-sm font-semibold">
          {t("previewLabel")} <span className="font-normal text-ink-2">{d.template_body ? t("previewExact") : t("previewSample")}</span>
        </figcaption>
        <blockquote className="rounded-control border border-divider bg-canvas p-3 text-sm" data-testid="wa-template-preview">
          {preview}
        </blockquote>
        <p className="text-xs text-ink-2">{t("previewNote")}</p>
      </figure>

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" disabled={busy !== null || !d.ready} onClick={() => void send("test")}>
          {busy === "test" ? t("sending") : t("sendTest")}
        </Button>
        <Button type="button" size="sm" variant="secondary" disabled={busy !== null || !d.ready} onClick={() => void send("schedule")}>
          {busy === "schedule" ? t("sending") : t("schedule")}
        </Button>
        <span className="text-sm text-ink-2">{t("left", { count: d.sends_left_this_hour })}</span>
      </div>
      <p className="text-sm text-ink-2">{t("closeTab")}</p>
      {note ? (
        <p role="status" className={cn("text-sm", note.tone === "urgent" ? "text-urgent" : "text-ink")}>
          {note.text}
        </p>
      ) : null}

      {d.history.length === 0 ? (
        <p className="text-sm text-ink-2">{t("none")}</p>
      ) : (
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-labelledby="wa-demo-h">
          <table className="w-full min-w-[34rem] text-left text-sm" data-testid="wa-history">
            <thead>
              <tr className="border-b border-divider">
                <th scope="col" className="py-2 pr-3">{t("colWhen")}</th>
                <th scope="col" className="py-2 pr-3">{t("colWhat")}</th>
                <th scope="col" className="py-2 pr-3">{t("colStatus")}</th>
                <th scope="col" className="py-2">{t("colSid")}</th>
              </tr>
            </thead>
            <tbody>
              {d.history.map((i) => {
                const k = statusKey(i, now);
                return (
                  <tr key={i.id} className="border-b border-divider align-top last:border-0">
                    <td className="py-2 pr-3 whitespace-nowrap">{formatDateTime(i.scheduled_for, locale, IST)} IST</td>
                    <td className="py-2 pr-3">{i.kind === "test" ? t("kindTest") : t("kindReminder")}</td>
                    <td className="py-2 pr-3">
                      <span className="inline-flex items-center gap-1">
                        <StatusIcon k={k} />
                        {t(`status.${k}`)}
                      </span>
                      {i.provider_status_at && i.state === "sent" ? (
                        <span className="block text-xs text-ink-2">{t("updated", { time: formatDateTime(i.provider_status_at, locale, IST) })}</span>
                      ) : null}
                      {i.explanation ? <span className="block text-xs text-urgent">{i.explanation}</span> : null}
                      {i.state === "queued" && i.kind === "demo_reminder" ? (
                        <Button type="button" size="sm" variant="quiet" className="mt-1" onClick={() => void cancel(i.id)}>
                          {t("cancel")}
                        </Button>
                      ) : null}
                    </td>
                    <td className="py-2 font-mono text-xs break-all">{i.message_sid ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-ink-2 [overflow-wrap:anywhere]">{d.callback_url ? t("callback", { url: d.callback_url }) : t("noCallback")}</p>
    </section>
  );
}
