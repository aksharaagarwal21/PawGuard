import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button, Notice } from "@pawguard/ui";

import { PublicPage } from "@/components/public-shell";
import { Link } from "@/i18n/navigation";
import { serverEnv } from "@/lib/server-env";

export const metadata: Metadata = { robots: { index: false, follow: false } };

async function confirm(token: string): Promise<boolean> {
  if (!/^[A-Za-z0-9_-]{20,100}$/.test(token)) return false;
  try {
    const r = await fetch(new URL("/api/v1/notify/confirm-email", serverEnv().PAWGUARD_API_INTERNAL_URL), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ token }),
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    return r.ok && ((await r.json()) as { confirmed: boolean }).confirmed;
  } catch {
    return false;
  }
}

/** The link in the confirmation email lands here; the one-time token is checked on the server. */
export default async function VerifyEmailPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("notify.verify");
  const ok = await confirm((await searchParams).token ?? "");
  return (
    <PublicPage locale={locale}>
      <div className="container-pg max-w-xl space-y-5 py-12">
        <h1 className="text-3xl">{ok ? t("okTitle") : t("failTitle")}</h1>
        <Notice tone={ok ? "success" : "neutral"}>{ok ? t("okBody") : t("failBody")}</Notice>
        <Button asChild>
          <Link href="/app/notifications">{t("open")}</Link>
        </Button>
      </div>
    </PublicPage>
  );
}
