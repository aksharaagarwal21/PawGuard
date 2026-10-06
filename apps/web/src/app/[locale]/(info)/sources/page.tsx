import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatusChip } from "@pawguard/ui";

import { PUBLIC_SOURCES } from "@/content/public-sources";

import { SimplePage } from "../simple-page";

export default async function SourcesPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("sources");
  const tc = await getTranslations("common");
  return (
    <SimplePage locale={locale} title={t("title")}>
      <p>{t("intro")}</p>
      <ul className="space-y-4 text-base">
        {PUBLIC_SOURCES.map((s) => (
          <li key={s.id} className="rounded-card border border-divider bg-surface p-4">
            <p className="font-display font-semibold">
              <a href={s.url} rel="noopener noreferrer" target="_blank">
                {s.title}
              </a>
            </p>
            <p className="text-sm text-ink-2">{s.publisher}</p>
            <p className="mt-2">
              <span className="font-semibold">{t("columns.used")}: </span>
              {s.usedFor}
            </p>
            <p className="mt-2 flex flex-wrap items-center gap-3 text-sm">
              <span>{tc("checked", { date: s.checked })}</span>
              <StatusChip kind={s.reviewStatus === "approved" ? "verified" : "submitted"}>
                {tc(`reviewStatus.${s.reviewStatus}`)}
              </StatusChip>
            </p>
          </li>
        ))}
      </ul>
    </SimplePage>
  );
}
