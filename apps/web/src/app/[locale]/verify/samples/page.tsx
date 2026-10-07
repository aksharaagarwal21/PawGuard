import type { Schemas } from "@pawguard/api-client";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Notice } from "@pawguard/ui";

import { PublicPage } from "@/components/public-shell";
import { SampleActions } from "@/components/verify/sample-actions";
import { Link } from "@/i18n/navigation";
import { serverEnv } from "@/lib/server-env";

export const metadata: Metadata = { robots: { index: false } };

/** Demo mode only: three sample certificates from the fictional demo clinics to scan with a phone. */
export default async function SamplesPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  if (!serverEnv().demoMode) notFound();
  const t = await getTranslations("verify.samples");
  let data: Schemas["DemoSamplesOut"] | null = null;
  try {
    const r = await fetch(new URL("/api/v1/public/demo-certificates", serverEnv().PAWGUARD_API_INTERNAL_URL), { cache: "no-store" });
    if (r.ok) data = (await r.json()) as Schemas["DemoSamplesOut"];
  } catch {
    data = null;
  }
  const items = [
    { key: "genuine", sample: data?.genuine },
    { key: "altered", sample: data?.altered },
    { key: "cancelled", sample: data?.cancelled },
  ] as const;
  return (
    <PublicPage locale={locale}>
      <div className="container-pg space-y-6 py-8">
        <h1 className="text-3xl">{t("title")}</h1>
        <Notice tone="info">{t("intro")}</Notice>
        {!data ? <Notice tone="urgent">{t("unavailable")}</Notice> : null}
        <ul className="grid gap-6 md:grid-cols-3">
          {items.map(({ key, sample }) => (
            <li key={key} className="space-y-2 rounded-card border border-divider bg-surface p-4" data-testid={`sample-${key}`}>
              <h2 className="text-lg">{t(`${key}.title`)}</h2>
              <p className="text-sm text-ink-2">{t(`${key}.body`)}</p>
              {sample?.qr_svg ? (
                <div className="mx-auto w-full max-w-64 bg-white p-2 [&>svg]:h-auto [&>svg]:w-full" dangerouslySetInnerHTML={{ __html: sample.qr_svg }} />
              ) : (
                <p className="text-sm">{t("missing")}</p>
              )}
              {sample?.qr_text ? (
                <>
                  <SampleActions qr={sample.qr_text} />
                  <details>
                    <summary className="cursor-pointer text-sm">{t("showText")}</summary>
                    <p className="mt-1 font-mono text-xs break-all whitespace-pre-wrap" data-qr-text>
                      {sample.qr_text}
                    </p>
                  </details>
                </>
              ) : null}
            </li>
          ))}
        </ul>
        <p>
          <Link href="/verify">{t("back")}</Link>
        </p>
      </div>
    </PublicPage>
  );
}
