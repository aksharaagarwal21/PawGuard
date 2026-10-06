import { getTranslations, setRequestLocale } from "next-intl/server";

import { Card, EmptyState, Notice, StatusChip } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { Link } from "@/i18n/navigation";
import { pageContext } from "@/lib/page-context";

import { NewCampaign } from "./new-campaign";

export default async function CampaignsPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  const t = await getTranslations("campaigns");
  const te = await getTranslations("errors");
  if (!ctx.can("campaign.manage")) {
    return (
      <PageBody>
        <Notice tone="urgent" title={te("forbiddenTitle")}>
          {te("forbiddenBody")}
        </Notice>
      </PageBody>
    );
  }
  const [{ data: campaigns }, { data: areas }] = await Promise.all([ctx.api.GET("/api/v1/campaigns"), ctx.api.GET("/api/v1/areas")]);
  return (
    <PageBody wide>
      <PageHeader title={t("title")} intro={t("intro")} />
      {campaigns && campaigns.length ? (
        <ul className="space-y-2">
          {campaigns.map((c) => (
            <li key={c.id}>
              <Card className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <Link href={`/app/campaigns/${c.id}`} className="font-display font-semibold">
                    {c.name}
                  </Link>
                  <p className="text-sm text-ink-2">
                    {t(`activity.${c.activity}` as "activity.vaccination")}
                    {c.starts_on ? ` · ${c.starts_on}${c.ends_on ? ` – ${c.ends_on}` : ""}` : ""}
                  </p>
                </div>
                <StatusChip kind="neutral">{t(`state.${c.state}` as "state.draft")}</StatusChip>
              </Card>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState title={t("none")} />
      )}
      <Card>
        <NewCampaign areas={(areas ?? []).map((a) => ({ id: a.id, name: a.name }))} />
      </Card>
    </PageBody>
  );
}
