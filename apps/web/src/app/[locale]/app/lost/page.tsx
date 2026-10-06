import { getTranslations, setRequestLocale } from "next-intl/server";

import { Card, EmptyState, Notice, StatusChip } from "@pawguard/ui";

import { MarkFoundButton, MessageList, OwnerReply } from "@/components/lost/lost-forms";
import { PageBody, PageHeader } from "@/components/page-header";
import { Link } from "@/i18n/navigation";
import { formatPartialDate } from "@/lib/format";
import { pageContext } from "@/lib/page-context";

/** Lost & found: the owner's lost reports and private conversations with finders. */
export default async function LostPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  const t = await getTranslations("lost");
  const { data, error } = await ctx.api.GET("/api/v1/my/lost");
  const reports = data ?? [];
  // Opening this page counts as reading the finders' messages.
  await Promise.all(
    reports.flatMap((r) =>
      r.threads
        .filter((th) => th.unread > 0)
        .map((th) => ctx.api.POST("/api/v1/my/lost/threads/{thread_id}/read", { params: { path: { thread_id: th.id } } })),
    ),
  );
  return (
    <PageBody>
      <PageHeader title={t("title")} intro={t("intro")} />
      {error ? <Notice tone="urgent">{t("loadFailed")}</Notice> : null}
      {reports.length === 0 && !error ? (
        <EmptyState title={t("emptyTitle")}>{t("emptyBody")}</EmptyState>
      ) : null}
      {reports.map((r) => (
        <section key={r.report_id} aria-labelledby={`lost-${r.report_id}`} className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id={`lost-${r.report_id}`} className="text-xl">
              <Link href={`/app/pets/${r.pet_id}`}>{r.pet_name}</Link>
            </h2>
            {r.state === "open" ? <StatusChip kind="rejected">{t("stateOpen")}</StatusChip> : <StatusChip kind="verified">{t("stateFound")}</StatusChip>}
          </div>
          <p className="text-sm text-ink-2">
            {t("reportedLine", {
              date: formatPartialDate(r.last_seen_on, "day", locale, t("unknownDate")),
              area: r.area_text ?? t("unknownArea"),
            })}
          </p>
          {r.state === "open" ? <MarkFoundButton petId={r.pet_id} /> : null}
          {r.threads.length === 0 ? (
            <p className="text-ink-2">{r.state === "open" ? t("noMessagesYet") : t("noMessages")}</p>
          ) : (
            r.threads.map((th) => (
              <Card key={th.id} className="space-y-3">
                <p className="text-sm font-semibold">
                  {th.finder_contact ? t("finderShared", { contact: th.finder_contact }) : t("finderNoContact")}
                </p>
                <MessageList messages={th.messages} me="owner" tz={ctx.tz} />
                {r.state === "open" ? <OwnerReply threadId={th.id} /> : null}
              </Card>
            ))
          )}
        </section>
      ))}
      <p className="text-sm text-ink-2">{t("privacyOwner")}</p>
    </PageBody>
  );
}
