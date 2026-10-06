import { getTranslations, setRequestLocale } from "next-intl/server";

import { EmptyState, StatusChip } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { Link } from "@/i18n/navigation";
import { pageContext } from "@/lib/page-context";

export default async function MergesPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  const t = await getTranslations("merge");
  const { data } = await ctx.api.GET("/api/v1/animal-merges");
  const items = data ?? [];
  return (
    <PageBody>
      <PageHeader title={t("title")} intro={t("intro")} />
      {items.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <ul className="divide-y divide-divider rounded-card border border-divider bg-surface">
          {items.map((m) => (
            <li key={m.id}>
              <Link href={`/app/merges/${m.id}`} className="flex flex-wrap items-center justify-between gap-2 p-4 text-ink no-underline hover:bg-canvas">
                <span className="font-mono text-sm font-semibold">
                  {m.source_reference} → {m.target_reference}
                </span>
                <StatusChip kind={m.state === "executed" ? "verified" : m.state === "proposed" ? "submitted" : "neutral"}>
                  {t(`states.${m.state}`)}
                </StatusChip>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </PageBody>
  );
}
