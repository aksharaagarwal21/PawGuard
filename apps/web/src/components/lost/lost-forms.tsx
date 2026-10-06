"use client";

import type { Schemas } from "@pawguard/api-client";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { Button, Field, Notice, TextInput, Textarea, cn } from "@pawguard/ui";

import { Link, useRouter } from "@/i18n/navigation";
import { browserApi, parseApiError } from "@/lib/api-browser";
import { formatDateTime } from "@/lib/format";

type Msg = Schemas["LostMessageOut"];

/** Owner: report the pet lost (date, area in words, note). */
export function ReportLostForm({ petId, petName, today }: { petId: string; petName: string; today: string }) {
  const t = useTranslations("lost");
  const router = useRouter();
  const [date, setDate] = useState(today);
  const [area, setArea] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const { error: apiError } = await browserApi.POST("/api/v1/my/pets/{pet_id}/lost", {
      params: { path: { pet_id: petId } },
      body: { last_seen_on: date || null, area_text: area.trim() || null, note: note.trim() || null },
    });
    setBusy(false);
    if (apiError) return setError(parseApiError(apiError).message || t("failed"));
    router.refresh();
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <p className="text-sm text-ink-2">{t("reportIntro", { name: petName })}</p>
      <Field id="lost-date" label={t("lastSeenOn")}>
        {(aria) => <TextInput {...aria} type="date" max={today} value={date} onChange={(e) => setDate(e.target.value)} />}
      </Field>
      <Field id="lost-area" label={t("area")} hint={t("areaHint")} marker={t("optional")}>
        {(aria) => <TextInput {...aria} maxLength={120} value={area} onChange={(e) => setArea(e.target.value)} />}
      </Field>
      <Field id="lost-note" label={t("note")} hint={t("noteHint")} marker={t("optional")}>
        {(aria) => <Textarea {...aria} maxLength={300} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />}
      </Field>
      {error ? <p className="font-semibold text-urgent">{error}</p> : null}
      <Button type="submit" variant="danger" disabled={busy}>
        {t("report")}
      </Button>
    </form>
  );
}

export function MarkFoundButton({ petId }: { petId: string }) {
  const t = useTranslations("lost");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  return (
    <Button
      type="button"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        await browserApi.POST("/api/v1/my/pets/{pet_id}/found", { params: { path: { pet_id: petId } } });
        setBusy(false);
        router.refresh();
      }}
    >
      {t("markFound")}
    </Button>
  );
}

/** A conversation as chat bubbles. `me` is whose side is on the right. */
export function MessageList({ messages, me, tz }: { messages: Msg[]; me: "owner" | "finder"; tz: string }) {
  const t = useTranslations("lost");
  const locale = useLocale();
  return (
    <ol className="space-y-2" aria-label={t("conversation")}>
      {messages.map((m, i) => (
        <li key={i} className={cn("flex", m.sender === me ? "justify-end" : "justify-start")}>
          <div className={cn("max-w-[85%] rounded-card p-3", m.sender === me ? "bg-primary text-white" : "border border-divider bg-surface")}>
            <p className="text-xs font-semibold opacity-80">
              {m.sender === "owner" ? t("ownerLabel") : t("finderLabel")} · {formatDateTime(m.created_at, locale, tz)}
            </p>
            <p className="whitespace-pre-line">{m.body}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

/** Owner reply box for one conversation. */
export function OwnerReply({ threadId }: { threadId: string }) {
  const t = useTranslations("lost");
  const router = useRouter();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="flex items-end gap-2"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!text.trim()) return;
        const { error: apiError } = await browserApi.POST("/api/v1/my/lost/threads/{thread_id}/reply", {
          params: { path: { thread_id: threadId } },
          body: { message: text.trim() },
        });
        if (apiError) return setError(parseApiError(apiError).message || t("failed"));
        setText("");
        setError(null);
        router.refresh();
      }}
    >
      <label className="min-w-0 flex-1">
        <span className="sr-only">{t("replyLabel")}</span>
        <Textarea value={text} maxLength={500} rows={2} placeholder={t("replyPlaceholder")} onChange={(e) => setText(e.target.value)} />
      </label>
      <Button type="submit">{t("send")}</Button>
      {error ? <p className="text-sm font-semibold text-urgent">{error}</p> : null}
    </form>
  );
}

/** Public QR card: "I found this pet" — write privately to the owner, then keep the private link. */
export function FinderStartForm({ cardToken }: { cardToken: string }) {
  const t = useTranslations("lost.finder");
  const [message, setMessage] = useState("");
  const [contact, setContact] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [link, setLink] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!message.trim()) return setError(t("messageRequired"));
    setBusy(true);
    const { data, error: apiError } = await browserApi.POST("/api/v1/public/cards/{token}/found", {
      params: { path: { token: cardToken } },
      body: { message: message.trim(), contact: contact.trim() || null },
    });
    setBusy(false);
    if (!data) return setError(parseApiError(apiError).message || t("failed"));
    setLink(`${window.location.origin}/${document.documentElement.lang || "en"}/found/${data.conversation_token}`);
  }

  if (link)
    return (
      <Notice tone="success" title={t("sentTitle")} live="polite">
        <p>{t("sentBody")}</p>
        <p className="break-all font-semibold">
          <a href={link}>{link}</a>
        </p>
      </Notice>
    );
  return (
    <form onSubmit={submit} className="space-y-3">
      <Field id="finder-message" label={t("message")} hint={t("messageHint")} error={error ?? undefined}>
        {(aria) => <Textarea {...aria} maxLength={500} rows={3} value={message} onChange={(e) => setMessage(e.target.value)} />}
      </Field>
      <Field id="finder-contact" label={t("contact")} hint={t("contactHint")} marker={t("optional")}>
        {(aria) => <TextInput {...aria} maxLength={120} value={contact} onChange={(e) => setContact(e.target.value)} />}
      </Field>
      <Button type="submit" disabled={busy}>
        {t("send")}
      </Button>
      <p className="text-xs text-ink-2">{t("privacy")}</p>
    </form>
  );
}

/** Finder's private page: write again. */
export function FinderReply({ token }: { token: string }) {
  const t = useTranslations("lost");
  const router = useRouter();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="flex items-end gap-2"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!text.trim()) return;
        const { error: apiError } = await browserApi.POST("/api/v1/public/found/{token}/messages", {
          params: { path: { token } },
          body: { message: text.trim() },
        });
        if (apiError) return setError(parseApiError(apiError).message || t("failed"));
        setText("");
        setError(null);
        router.refresh();
      }}
    >
      <label className="min-w-0 flex-1">
        <span className="sr-only">{t("replyLabel")}</span>
        <Textarea value={text} maxLength={500} rows={2} placeholder={t("replyPlaceholder")} onChange={(e) => setText(e.target.value)} />
      </label>
      <Button type="submit">{t("send")}</Button>
      {error ? <p className="text-sm font-semibold text-urgent">{error}</p> : null}
    </form>
  );
}

export function LostLink({ count }: { count: number }) {
  const t = useTranslations("lost");
  return <Link href="/app/lost">{t("openMessages", { count })}</Link>;
}
