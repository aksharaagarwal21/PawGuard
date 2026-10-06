import type { Schemas } from "@pawguard/api-client";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Card, Notice, StatusChip } from "@pawguard/ui";

import { FinderReply, MessageList } from "@/components/lost/lost-forms";
import { PublicPage } from "@/components/public-shell";
import { serverEnv } from "@/lib/server-env";

export const metadata: Metadata = { robots: { index: false, follow: false } };

async function load(token: string): Promise<Schemas["FinderThreadOut"] | null> {
  if (!/^[A-Za-z0-9_-]{20,100}$/.test(token)) return null;
  try {
    const r = await fetch(new URL(`/api/v1/public/found/${token}`, serverEnv().PAWGUARD_API_INTERNAL_URL), {
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    return r.ok ? ((await r.json()) as Schemas["FinderThreadOut"]) : null;
  } catch {
    return null;
  }
}

/** The finder's private conversation with a lost pet's owner (no account needed; keep the link). */
export default async function FinderPage({ params }: { params: Promise<{ locale: string; token: string }> }) {
  const { locale, token } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("lost.finder");
  const thread = await load(token);
  return (
    <PublicPage locale={locale}>
      <div className="container-pg max-w-2xl space-y-5 py-10">
        {!thread ? (
          <Notice tone="neutral" title={t("notFoundTitle")}>{t("notFoundBody")}</Notice>
        ) : (
          <>
            <h1 className="text-3xl">{t("threadTitle", { name: thread.pet_name })}</h1>
            <div className="flex flex-wrap gap-2">
              {thread.found ? <StatusChip kind="verified">{t("isFound")}</StatusChip> : <StatusChip kind="rejected">{t("isLost")}</StatusChip>}
              {thread.is_demo ? <StatusChip kind="demo">{t("demo")}</StatusChip> : null}
            </div>
            <p className="text-ink-2">{t("threadIntro", { clinic: thread.clinic })}</p>
            <Card className="space-y-3">
              <MessageList messages={thread.messages} me="finder" tz="Asia/Kolkata" />
              {thread.open ? <FinderReply token={token} /> : <p className="text-sm text-ink-2">{t("closed")}</p>}
            </Card>
            <p className="text-sm text-ink-2">{t("keepLink")}</p>
          </>
        )}
      </div>
    </PublicPage>
  );
}
