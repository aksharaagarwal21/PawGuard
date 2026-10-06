import { getTranslations, setRequestLocale } from "next-intl/server";

import { Notice } from "@pawguard/ui";

import { AssistantChat } from "@/components/assistant/assistant-chat";
import { PageBody, PageHeader } from "@/components/page-header";
import { pageContext } from "@/lib/page-context";

/** Ask PawGuard: short answers about the app and your own reminders. Never treatment advice. */
export default async function AssistantPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  const t = await getTranslations("assistant");
  const { data } = await ctx.api.GET("/api/v1/my/assistant");
  return (
    <PageBody>
      <PageHeader title={t("title")} intro={t("intro")} />
      {data ? <AssistantChat status={data} /> : <Notice tone="urgent">{t("failed")}</Notice>}
    </PageBody>
  );
}
