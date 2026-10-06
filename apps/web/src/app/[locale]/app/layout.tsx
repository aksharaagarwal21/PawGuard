import { getTranslations, setRequestLocale } from "next-intl/server";

import { EmptyState, Notice, ToastProvider } from "@pawguard/ui";

import { AppShell } from "@/components/app-shell";
import { PublicPage } from "@/components/public-shell";
import { redirect } from "@/i18n/navigation";
import { activeMembership, getMe } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function AppLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const result = await getMe();
  if (result.state === "signed_out") {
    redirect({ href: "/sign-in?expired=1", locale });
    return null;
  }
  if (result.state === "unavailable") {
    const t = await getTranslations("errors");
    return (
      <PublicPage locale={locale}>
        <div className="container-pg py-10">
          <Notice tone="urgent" title={t("unavailableTitle")} live="alert">
            {t("unavailableBody")}
          </Notice>
        </div>
      </PublicPage>
    );
  }
  const active = await activeMembership(result.me);
  if (!active) {
    const t = await getTranslations("app");
    return (
      <PublicPage locale={locale}>
        <div className="container-pg py-10">
          <EmptyState title={t("noOrganisations")}>{t("noOrganisationsBody")}</EmptyState>
        </div>
      </PublicPage>
    );
  }
  const tc = await getTranslations("common");
  return (
    <ToastProvider closeLabel={tc("close")}>
      <AppShell me={result.me} active={active} locale={locale}>
        {children}
      </AppShell>
    </ToastProvider>
  );
}
