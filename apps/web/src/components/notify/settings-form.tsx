"use client";

import type { Schemas } from "@pawguard/api-client";
import { BellRing, Mail, MessageCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button, Field, Notice, TextInput } from "@pawguard/ui";

import { useRouter } from "@/i18n/navigation";
import { browserApi, parseApiError, type FieldErrors } from "@/lib/api-browser";

import { PushToggle } from "./push-toggle";

type Settings = Schemas["NotificationSettingsOut"];
type Channel = "email" | "push" | "whatsapp";

/** Opt-in channels for vaccination reminders, with a test message per channel. */
export function NotificationSettingsForm({ initial, vapidKey }: { initial: Settings; vapidKey: string | null }) {
  const t = useTranslations("notify");
  const tc = useTranslations("common");
  const router = useRouter();
  const [s, setS] = useState(initial);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [message, setMessage] = useState<{ tone: "success" | "urgent"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function save(next: Settings) {
    setBusy(true);
    setErrors({});
    setMessage(null);
    const { data, error } = await browserApi.PUT("/api/v1/my/notification-settings", {
      body: {
        email_enabled: next.email_enabled,
        email_address: next.email_address || null,
        push_enabled: next.push_enabled,
        whatsapp_enabled: next.whatsapp_enabled,
        whatsapp_number: next.whatsapp_number || null,
      },
    });
    setBusy(false);
    if (!data) {
      const p = parseApiError(error);
      setErrors(p.fields);
      setMessage({ tone: "urgent", text: p.message || tc("tryAgainLater") });
      return false;
    }
    setS(data);
    setMessage({ tone: "success", text: t("saved") });
    router.refresh();
    return true;
  }

  async function test(channel: Channel) {
    setMessage(null);
    const { error, response } = await browserApi.POST("/api/v1/my/notification-settings/test", { body: { channel } });
    if (response.status === 202) return setMessage({ tone: "success", text: t(`testQueued.${channel}`) });
    const p = parseApiError(error);
    const text =
      p.code === "rate_limited" ? t("testLimited") : p.code === "email_not_confirmed" ? t("email.confirmFirst") : p.message || tc("tryAgainLater");
    setMessage({ tone: "urgent", text });
  }

  async function resend() {
    setMessage(null);
    const { error, response } = await browserApi.POST("/api/v1/my/notification-settings/resend-confirmation");
    if (response.status === 202) return setMessage({ tone: "success", text: t("email.resent") });
    const p = parseApiError(error);
    setMessage({ tone: "urgent", text: p.code === "rate_limited" ? t("testLimited") : p.message || tc("tryAgainLater") });
  }

  const row = (
    channel: Channel,
    Icon: typeof Mail,
    enabled: boolean,
    toggle: (v: boolean) => Settings,
    extra?: React.ReactNode,
  ) => (
    <section aria-labelledby={`ch-${channel}`} className="space-y-3 rounded-card border border-divider bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-sage text-primary">
            <Icon aria-hidden className="size-5" />
          </span>
          <div className="min-w-0">
            <h2 id={`ch-${channel}`} className="text-lg">{t(`${channel}.title`)}</h2>
            <p className="text-sm text-ink-2">{t(`${channel}.body`)}</p>
          </div>
        </div>
        {s.available[channel] && channel === "push" ? (
          <span className="rounded-full border border-control px-3 py-1 text-sm font-semibold">
            {s.push_devices > 0 ? t("on") : t("off")}
          </span>
        ) : s.available[channel] ? (
          <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 font-semibold">
            <input
              type="checkbox"
              className="size-5 accent-primary"
              checked={enabled}
              disabled={busy}
              onChange={(e) => void save(toggle(e.target.checked))}
            />
            {enabled ? t("on") : t("off")}
          </label>
        ) : (
          <span className="rounded-full border border-control px-3 py-1 text-sm text-ink-2">{t("notSetUp")}</span>
        )}
      </div>
      {s.available[channel] ? extra : <p className="text-sm text-ink-2">{t(`${channel}.unavailable`)}</p>}
      {s.available[channel] ? (
        <Button type="button" size="sm" variant="secondary" onClick={() => void test(channel)}>
          {t("sendTest")}
        </Button>
      ) : null}
    </section>
  );

  return (
    <div className="space-y-4">
      {s.demo_recipients ? <Notice tone="info" title={t("demoTitle")}>{t("demoBody")}</Notice> : null}
      {message ? (
        <Notice tone={message.tone} live="polite">
          {message.text}
        </Notice>
      ) : null}
      {row("email", Mail, s.email_enabled, (v) => ({ ...s, email_enabled: v }),
        <div className="space-y-3">
        {s.email_address && !s.demo_recipients ? (
          s.email_verified ? (
            <p className="text-sm font-semibold">{t("email.confirmed", { address: s.email_address })}</p>
          ) : (
            <div className="space-y-2 rounded-control bg-sand p-3 text-sm">
              <p>{s.email_pending ? t("email.pending", { address: s.email_address }) : t("email.notConfirmed")}</p>
              <Button type="button" size="sm" variant="secondary" onClick={() => void resend()}>
                {t("email.resend")}
              </Button>
            </div>
          )
        ) : null}
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void save(s);
          }}
        >
          <Field id="notify-email" label={t("email.address")} hint={t("email.addressHint")} error={errors.email_address} className="min-w-0 flex-1">
            {(aria) => (
              <TextInput
                {...aria}
                type="email"
                autoComplete="email"
                value={s.email_address ?? ""}
                onChange={(e) => setS({ ...s, email_address: e.target.value })}
              />
            )}
          </Field>
          <Button type="submit" variant="secondary" disabled={busy}>
            {tc("save")}
          </Button>
        </form>
        </div>,
      )}
      {row("push", BellRing, s.push_enabled, (v) => ({ ...s, push_enabled: v }),
        <PushToggle vapidKey={vapidKey} devices={s.push_devices} onChanged={() => router.refresh()} />,
      )}
      {row("whatsapp", MessageCircle, s.whatsapp_enabled, (v) => ({ ...s, whatsapp_enabled: v }),
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void save(s);
          }}
        >
          <Field id="notify-wa" label={t("whatsapp.number")} hint={t("whatsapp.numberHint")} error={errors.whatsapp_number} className="min-w-0 flex-1">
            {(aria) => (
              <TextInput
                {...aria}
                type="tel"
                autoComplete="tel"
                placeholder="+91…"
                value={s.whatsapp_number ?? ""}
                onChange={(e) => setS({ ...s, whatsapp_number: e.target.value })}
              />
            )}
          </Field>
          <Button type="submit" variant="secondary" disabled={busy}>
            {tc("save")}
          </Button>
        </form>,
      )}
      <p className="text-sm text-ink-2">{t("footer")}</p>
    </div>
  );
}
