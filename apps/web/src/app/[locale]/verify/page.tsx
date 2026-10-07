import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { PublicPage } from "@/components/public-shell";
import { Verifier } from "@/components/verify/verifier";
import { serverEnv } from "@/lib/server-env";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "verify" });
  return { title: t("title"), manifest: "/verify.webmanifest", robots: { index: true } };
}

/** Public certificate verifier (no account). Verification runs in the browser and works offline after one visit. */
export default async function VerifyPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("verify");
  return (
    <PublicPage locale={locale}>
      <div className="container-pg max-w-2xl space-y-4 py-8">
        <h1 className="text-3xl">{t("title")}</h1>
        <p className="prose-pg text-lg">{t("intro")}</p>
        <Verifier demoSamples={serverEnv().demoMode} />
      </div>
    </PublicPage>
  );
}
