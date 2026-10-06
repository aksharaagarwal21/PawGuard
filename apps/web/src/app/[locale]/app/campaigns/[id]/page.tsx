import { getTranslations, setRequestLocale } from "next-intl/server";

import { Notice } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { pageContext } from "@/lib/page-context";

import { Planner } from "./planner";

export default async function CampaignPage({ params, searchParams }: {
  params: Promise<{ locale: string; id: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  const sp = await searchParams;
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
  const [{ data: campaign }, { data: teams }, { data: plans }] = await Promise.all([
    ctx.api.GET("/api/v1/campaigns/{campaign_id}", { params: { path: { campaign_id: id } } }),
    ctx.api.GET("/api/v1/teams"),
    ctx.api.GET("/api/v1/campaigns/{campaign_id}/plans", { params: { path: { campaign_id: id } } }),
  ]);
  if (!campaign) {
    return (
      <PageBody>
        <Notice tone="urgent" title={te("notFoundTitle")}>
          {te("notFoundBody")}
        </Notice>
      </PageBody>
    );
  }
  const selected = (plans ?? []).find((p) => p.id === sp.plan) ?? plans?.[0] ?? null;
  return (
    <PageBody wide>
      <PageHeader title={campaign.name} intro={t("plannerIntro")} back={{ href: "/app/campaigns", label: t("title") }} />
      <Planner
        campaign={campaign}
        teams={teams ?? []}
        plans={plans ?? []}
        selected={selected}
        canPublish={ctx.can("task.manage")}
        defaultDate={campaign.starts_on ?? new Date().toISOString().slice(0, 10)}
      />
    </PageBody>
  );
}
