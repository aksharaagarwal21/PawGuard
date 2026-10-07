"use client";

import type { Schemas } from "@pawguard/api-client";
import { HeartPulse, Mic, MicOff, Send, Square } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { Button, Notice, cn } from "@pawguard/ui";

import { Link } from "@/i18n/navigation";
import { browserApi, parseApiError } from "@/lib/api-browser";

import { createRecognition, recognitionSupported, speak, stopSpeaking, voicesFor, type Recognition } from "./voice";

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
  // Voice: browser speech recognition in, the device's voices out; text is always shown too.
  const [listening, setListening] = useState(false);
  const [heard, setHeard] = useState("");
  const [speaking, setSpeaking] = useState(false);
  const [voice, setVoice] = useState<SpeechSynthesisVoice | null>(null);
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  const [canListen, setCanListen] = useState(false);
  const recRef = useRef<Recognition | null>(null);

  useEffect(() => {
    let cancelled = false;
    const raf = requestAnimationFrame(async () => {
      setCanListen(recognitionSupported());
      const found = await voicesFor(lang);
      if (cancelled) return;
      setVoice(found[0] ?? null);
      setVoiceNote(found.length ? null : t("voice.noVoice", { language: t(`voice.languages.${lang}`) }));
    });
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
    };
  }, [lang, t]);

  function listen() {
    if (listening) {
      recRef.current?.stop();
      return;
    }
    stopSpeaking();
    setSpeaking(false);
    // Brave ships the speech API but switches off the online recognition service behind it.
    if ((navigator as Navigator & { brave?: unknown }).brave) return setVoiceNote(t("voice.brave"));
    const rec = createRecognition(lang);
    if (!rec) return setVoiceNote(t("voice.noRecognition"));
    recRef.current = rec;
    let finalText = "";
    rec.onresult = (e) => {
      let interim = "";
      for (let i = 0; i < e.results.length; i++) {
        const r = e.results[i]!;
        if (r.isFinal) finalText += r[0]!.transcript;
        else interim += r[0]!.transcript;
      }
      setHeard(finalText || interim);
    };
    rec.onerror = (e) => {
      setVoiceNote(
        e.error === "not-allowed" || e.error === "service-not-allowed"
          ? t("voice.denied")
          : e.error === "no-speech"
            ? t("voice.noSpeech")
            : e.error === "network"
              ? t("voice.network")
              : t("voice.error"),
      );
    };
    rec.onend = () => {
      setListening(false);
      setHeard("");
      if (finalText.trim()) void send(finalText, true);
    };
    setVoiceNote(null);
    setListening(true);
    rec.start();
  }

  async function send(text: string, spoken = false) {
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
    if (spoken && voice) {
      setSpeaking(true);
      speak(data.reply, voice, () => setSpeaking(false));
    }
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
            onChange={(e) => {
              stopSpeaking();
              setSpeaking(false);
              setLang(e.target.value as Lang);
            }}
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

      <section aria-labelledby="voice-h" className="space-y-2 rounded-card border border-divider bg-surface p-4">
        <h2 id="voice-h" className="text-base">{t("voice.title")}</h2>
        {canListen ? (
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" onClick={listen} disabled={busy} variant={listening ? "secondary" : "primary"} aria-pressed={listening}>
              {listening ? <MicOff aria-hidden className="size-5" /> : <Mic aria-hidden className="size-5" />}
              {listening ? t("voice.stopListening") : t("voice.talk")}
            </Button>
            {speaking ? (
              <Button type="button" variant="secondary" onClick={() => { stopSpeaking(); setSpeaking(false); }}>
                <Square aria-hidden className="size-4" />
                {t("voice.stopSpeaking")}
              </Button>
            ) : null}
            {listening ? (
              <span role="status" className="text-sm">
                {heard ? t("voice.heard", { text: heard }) : t("voice.listening")}
              </span>
            ) : null}
          </div>
        ) : (
          <p className="text-sm">{t("voice.noRecognition")}</p>
        )}
        {voiceNote ? <p className="text-sm font-semibold">{voiceNote}</p> : null}
        <p className="text-xs text-ink-2">{t("voice.privacy")}</p>
      </section>

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
