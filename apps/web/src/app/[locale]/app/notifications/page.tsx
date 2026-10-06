import { getTranslations, setRequestLocale } from "next-intl/server";

import { Notice } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { NotificationSettingsForm } from "@/components/notify/settings-form";
import { pageContext } from "@/lib/page-context";

/** Choose how to get vaccination reminders: email, browser notifications, WhatsApp (all opt-in). */
export default async function NotificationsPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  const t = await getTranslations("notify");
  const [settings, key] = await Promise.all([
    ctx.api.GET("/api/v1/my/notification-settings"),
    ctx.api.GET("/api/v1/push/public-key"),
  ]);
  return (
    <PageBody>
      <PageHeader title={t("title")} intro={t("intro")} back={{ href: "/app/reminders", label: t("backToReminders") }} />
      {settings.data ? (
        <NotificationSettingsForm initial={settings.data} vapidKey={key.data?.public_key ?? null} />
      ) : (
        <Notice tone="urgent">{t("loadFailed")}</Notice>
      )}
    </PageBody>
  );
}
