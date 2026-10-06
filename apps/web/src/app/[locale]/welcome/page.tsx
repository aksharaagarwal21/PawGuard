import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button, Notice } from "@pawguard/ui";

import { PublicPage } from "@/components/public-shell";
import { Link } from "@/i18n/navigation";
import { serverEnv } from "@/lib/server-env";

const STEPS = ["one", "two", "three", "four"] as const;
const PET_STEPS = ["one", "two", "three", "four", "five"] as const;

/**
 * Demo welcome: how to try the demonstration, then "Let's start" → sign-in. Shown only while demo mode is on
 * (development/test with fictional data); in production this page does not exist.
 */
export default async function WelcomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  if (!serverEnv().demoMode) notFound();
  const t = await getTranslations("welcome");
  return (
    <PublicPage locale={locale}>
      <section className="container-pg max-w-3xl space-y-8 py-10 md:py-14">
        <header className="space-y-3">
          <h1 className="text-3xl md:text-4xl">{t("title")}</h1>
          <p className="text-lg text-ink-2">{t("intro")}</p>
        </header>

        <Notice tone="info" title={t("fictionalTitle")}>
          <p>{t("fictionalBody")}</p>
        </Notice>

        <section aria-labelledby="pet-how" className="space-y-4">
          <h2 id="pet-how" className="text-xl">{t("petHowTitle")}</h2>
          <ol className="space-y-3">
            {PET_STEPS.map((k, i) => (
              <li key={k} className="flex gap-4 rounded-card border border-divider bg-surface p-4">
                <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-primary font-display font-bold text-white">
                  {i + 1}
                </span>
                <div>
                  <p className="font-display font-semibold">{t(`petSteps.${k}.title`)}</p>
                  <p className="text-ink-2">{t(`petSteps.${k}.body`)}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="how" className="space-y-4">
          <h2 id="how" className="text-xl">{t("howTitle")}</h2>
          <ol className="space-y-3">
            {STEPS.map((k, i) => (
              <li key={k} className="flex gap-4 rounded-card border border-divider bg-surface p-4">
                <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-primary font-display font-bold text-white">
                  {i + 1}
                </span>
                <div>
                  <p className="font-display font-semibold">{t(`steps.${k}.title`)}</p>
                  <p className="text-ink-2">{t(`steps.${k}.body`)}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="files" className="space-y-3">
          <h2 id="files" className="text-xl">{t("filesTitle")}</h2>
          <p className="text-ink-2">{t("filesIntro")}</p>
          <ul className="space-y-2">
            <li>
              <a href="/demo/sample-dog.jpg" download>{t("sampleDog")}</a>
              <span className="block text-sm text-ink-2">{t("sampleDogCredit")}</span>
            </li>
            <li>
              <a href="/demo/sample-certificate.jpg" download>{t("sampleCertificate")}</a>
              <span className="block text-sm text-ink-2">{t("sampleCertificateNote")}</span>
            </li>
          </ul>
        </section>

        <Notice tone="pending" title={t("limitsTitle")}>
          <ul className="list-disc space-y-1 pl-5">
            <li>{t("limits.reminders")}</li>
            <li>{t("limits.matching")}</li>
            <li>{t("limits.offline")}</li>
            <li>{t("limits.language")}</li>
            <li>{t("limits.reset")}</li>
          </ul>
        </Notice>

        <div className="flex flex-wrap items-center gap-4">
          <Button asChild size="lg">
            <Link href="/sign-in">{t("start")}</Link>
          </Button>
          <Link href="/">{t("aboutLink")}</Link>
        </div>
      </section>
    </PublicPage>
  );
}
