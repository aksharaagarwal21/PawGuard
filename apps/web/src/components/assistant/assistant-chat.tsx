"use client";

import type { Schemas } from "@pawguard/api-client";
import { HeartPulse, Send } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useRef, useState } from "react";

import { Button, Notice, cn } from "@pawguard/ui";

import { Link } from "@/i18n/navigation";
import { browserApi, parseApiError } from "@/lib/api-browser";

type Action = Schemas["AssistantOut"]["actions"][number];
type Msg = { role: "user" | "assistant"; text: string; actions?: Action[]; guarded?: boolean };
type Lang = "en" | "hi" | "ta";

/** Links for the fixed action list; the model can only pick codes, never URLs. */
const ACTION_HREF: Record<Action, string> = {
  open_reminders: "/app/reminders",
  mark_done: "/app/reminders",
  add_calendar: "/app/reminders",
  open_pets: "/app/pets",
  open_card: "/app/pets",
  notifications: "/app/notifications",
  how_to: "/guide",
  bite_help: "/help",
};

export function AssistantChat({ status }: { status: Schemas["AssistantStatusOut"] }) {
  const t = useTranslations("assistant");
  const locale = useLocale();
  const [lang, setLang] = useState<Lang>((["en", "hi", "ta"].includes(locale) ? locale : "en") as Lang);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLOListElement>(null);

  async function send(text: string) {
    const clean = text.trim();
    if (!clean || busy) return;
    const next: Msg[] = [...messages, { role: "user", text: clean }];
    setMessages(next);
    setDraft("");
    setBusy(true);
    setError(null);
    const { data, error: apiError } = await browserApi.POST("/api/v1/my/assistant", {
      body: { language: lang, messages: next.slice(-10).map((m) => ({ role: m.role, text: m.text.slice(0, 1000) })) },
    });
    setBusy(false);
    if (!data) {
      const p = parseApiError(apiError);
      setError(p.code === "assistant_busy" || p.code === "rate_limited" ? t("busy") : p.message || t("failed"));
      return;
    }
    setMessages([...next, { role: "assistant", text: data.reply, actions: data.actions, guarded: data.guarded }]);
    requestAnimationFrame(() => listRef.current?.lastElementChild?.scrollIntoView({ block: "nearest" }));
  }

  if (!status.available) return <Notice tone="neutral" title={t("offTitle")}>{t("offBody")}</Notice>;

  return (
    <div className="space-y-4">
      <Notice tone="pending" title={t("previewTitle")}>
        <p>{t("previewBody")}</p>
        {status.shares_with_google ? <p className="font-semibold">{t("googleNote")}</p> : null}
      </Notice>

      <div className="flex flex-wrap items-center gap-3">
        <label className="inline-flex items-center gap-2 text-sm font-semibold">
          {t("language")}
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value as Lang)}
            className="min-h-11 rounded-control border border-control bg-surface px-2 font-normal"
          >
            <option value="en">English</option>
            <option value="hi">हिन्दी</option>
            <option value="ta">தமிழ்</option>
          </select>
        </label>
      </div>

      <ol ref={listRef} aria-live="polite" aria-label={t("conversation")} className="space-y-3">
        {messages.length === 0 ? (
          <li className="rounded-card border border-dashed border-control bg-surface p-4 text-ink-2">{t("empty")}</li>
        ) : null}
        {messages.map((m, i) => (
          <li key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
            <div
              className={cn(
                "max-w-[85%] space-y-2 rounded-card p-3",
                m.role === "user" ? "bg-primary text-white" : "border border-divider bg-surface",
              )}
            >
              <p className="sr-only">{m.role === "user" ? t("you") : t("assistantName")}</p>
              <p className="whitespace-pre-line">{m.text}</p>
              {m.guarded ? <p className="text-xs text-ink-2">{t("guarded")}</p> : null}
              {m.actions?.length ? (
                <div className="flex flex-wrap gap-2">
                  {m.actions.map((a) => (
                    <Link
                      key={a}
                      href={ACTION_HREF[a]}
                      className={cn(
                        "inline-flex min-h-11 items-center gap-1.5 rounded-control px-3 text-sm font-semibold no-underline",
                        a === "bite_help" ? "bg-urgent text-white" : "border border-control bg-surface text-ink hover:bg-sage",
                      )}
                    >
                      {a === "bite_help" ? <HeartPulse aria-hidden className="size-4" /> : null}
                      {t(`actions.${a}`)}
                    </Link>
                  ))}
                </div>
              ) : null}
            </div>
          </li>
        ))}
        {busy ? (
          <li className="text-sm text-ink-2" role="status">
            {t("thinking")}
          </li>
        ) : null}
      </ol>

      {error ? <Notice tone="urgent" live="polite">{error}</Notice> : null}

      {messages.length === 0 ? (
        <div className="flex flex-wrap gap-2">
          {(["attention", "waiting", "addPast"] as const).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => void send(t(`suggest.${k}`))}
              className="min-h-11 rounded-full border border-control bg-surface px-4 text-sm font-semibold hover:bg-sage"
            >
              {t(`suggest.${k}`)}
            </button>
          ))}
        </div>
      ) : null}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send(draft);
        }}
        className="flex items-end gap-2"
      >
        <label className="min-w-0 flex-1">
          <span className="sr-only">{t("inputLabel")}</span>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(draft);
              }
            }}
            maxLength={1000}
            rows={2}
            placeholder={t("placeholder")}
            className="w-full rounded-control border border-control bg-surface p-3"
          />
        </label>
        <Button type="submit" disabled={busy || !draft.trim()} aria-label={t("send")}>
          <Send aria-hidden className="size-5" />
        </Button>
      </form>
      <p className="text-sm text-ink-2">{t("footer")}</p>
    </div>
  );
}
