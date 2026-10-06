import { getTranslations, setRequestLocale } from "next-intl/server";

import { Notice } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { pageContext } from "@/lib/page-context";

import { SurveyForm } from "./survey-form";

export default async function NewSurveyPage({
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
  const t = await getTranslations("survey");
  const te = await getTranslations("errors");
  if (!ctx.can("survey.write")) {
    return (
      <PageBody>
        <Notice tone="urgent" title={te("forbiddenTitle")}>
          {te("forbiddenBody")}
        </Notice>
      </PageBody>
    );
  }
  const { data: areas } = await ctx.api.GET("/api/v1/areas");
  return (
    <PageBody>
      <PageHeader title={t("title")} intro={t("intro")} back={{ href: "/app/tasks", label: t("back") }} />
      <SurveyForm
        areas={(areas ?? []).map((a) => ({ id: a.id, name: a.name }))}
        defaultArea={sp.area ?? ""}
        taskId={sp.task ?? null}
        campaignId={sp.campaign ?? null}
      />
    </PageBody>
  );
}
