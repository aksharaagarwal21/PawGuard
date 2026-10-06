import { getTranslations, setRequestLocale } from "next-intl/server";

import { Card, EmptyState, Notice, StatusChip } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { Link } from "@/i18n/navigation";
import { formatDateTime } from "@/lib/format";
import { pageContext } from "@/lib/page-context";

import { ImportReport } from "./import-report";
import { ImportUpload } from "./import-upload";

export default async function ImportsPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const sp = await searchParams;
  const ctx = await pageContext();
  const t = await getTranslations("imports");
  const te = await getTranslations("errors");
  if (!ctx.can("data.import")) {
    return (
      <PageBody>
        <Notice tone="urgent" title={te("forbiddenTitle")}>
          {te("forbiddenBody")}
        </Notice>
      </PageBody>
    );
  }
  const [{ data: history }, detail] = await Promise.all([
    ctx.api.GET("/api/v1/imports"),
    sp.id ? ctx.api.GET("/api/v1/imports/{import_id}", { params: { path: { import_id: sp.id } } }) : Promise.resolve({ data: undefined }),
  ]);
  return (
    <PageBody wide>
      <PageHeader title={t("title")} intro={t("intro")} />
      {detail.data ? (
        <ImportReport job={detail.data} canRollback={ctx.can("animal.merge")} />
      ) : (
        <Card>
          <ImportUpload />
        </Card>
      )}
      <section aria-labelledby="hist" className="space-y-2">
        <h2 id="hist" className="text-lg">
          {t("history")}
        </h2>
        {history && history.length ? (
          <ul className="divide-y divide-divider rounded-card border border-divider bg-surface">
            {history.map((j) => (
              <li key={j.id}>
                <Link href={`/app/imports?id=${j.id}`} className="flex flex-wrap items-center justify-between gap-2 p-3 text-ink no-underline hover:bg-canvas">
                  <span>
                    <span className="font-display font-semibold">{j.source_label}</span>
                    <span className="block text-sm text-ink-2">
                      {t(`types.${j.import_type}`)} · {formatDateTime(j.created_at, locale, ctx.tz)} ·{" "}
                      {t("counts", { valid: j.valid_count, warning: j.warning_count, rejected: j.rejected_count })}
                    </span>
                  </span>
                  <StatusChip kind={j.state === "applied" ? "verified" : j.state === "validated" ? "submitted" : "neutral"}>
                    {t(`states.${j.state}`)}
                  </StatusChip>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title={t("noHistory")} />
        )}
      </section>
    </PageBody>
  );
}
