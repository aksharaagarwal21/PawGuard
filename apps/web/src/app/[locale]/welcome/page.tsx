import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Notice } from "@pawguard/ui";

import { RolePicker } from "@/components/landing/role-picker";
import { PublicPage } from "@/components/public-shell";
import { serverEnv } from "@/lib/server-env";

const STEPS = ["one", "two", "three", "four"] as const;
const PET_STEPS = ["one", "two", "three", "four", "five"] as const;

/**
 * "Before you begin" (the Get started page): choose how you'll use PawGuard, see the fictional demo accounts, then
 * continue to sign in. Shown only while demo mode is on (development/test with fictional data).
 */
export default async function WelcomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  if (!serverEnv().demoMode) notFound();
  const t = await getTranslations("welcome");
  const demoRows = (["neha", "kiran", "asha", "vikram", "priya"] as const).map((k) => ({
    name: t(`demo.${k}.name`),
    role: t(`demo.${k}.role`),
    tryFirst: t(`demo.${k}.try`),
    group: (k === "neha" ? "owner" : k === "priya" ? "volunteer" : "clinic") as "owner" | "clinic" | "volunteer",
  }));
  return (
    <PublicPage locale={locale}>
      <section className="container-pg max-w-4xl space-y-10 py-10 md:py-14">
        <header className="space-y-3">
          <h1 className="text-3xl md:text-4xl">
            <span className="mb-1 block font-body text-base font-semibold text-ink-2">{t("title")}</span>
            {t("beforeYouBegin")}
          </h1>
          <p className="max-w-prose text-lg text-ink-2">{t("beginIntro")}</p>
        </header>

        <Notice tone="info" title={t("fictionalTitle")}>
          <p>{t("fictionalBody")}</p>
        </Notice>

        <RolePicker demoRows={demoRows} />

        <details className="rounded-card border border-divider bg-surface p-4">
          <summary className="cursor-pointer font-display font-semibold">{t("walkthroughTitle")}</summary>
          <div className="mt-4 space-y-6">
            {(
              [
                ["petHowTitle", "petSteps", PET_STEPS],
                ["howTitle", "steps", STEPS],
              ] as const
            ).map(([title, ns, keys]) => (
              <section key={ns} className="space-y-3">
                <h2 className="text-lg">{t(title)}</h2>
                <ol className="space-y-2">
                  {keys.map((k, i) => (
                    <li key={k} className="flex gap-3">
                      <span aria-hidden className="grid size-7 shrink-0 place-items-center rounded-full bg-primary text-sm font-bold text-white">
                        {i + 1}
                      </span>
                      <div>
                        <p className="font-display font-semibold">{t(`${ns}.${k}.title`)}</p>
                        <p className="text-ink-2">{t(`${ns}.${k}.body`)}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              </section>
            ))}
            <section className="space-y-2">
              <h2 className="text-lg">{t("filesTitle")}</h2>
              <p className="text-ink-2">{t("filesIntro")}</p>
              <ul className="space-y-2">
                <li>
                  <a href="/demo/sample-certificate.jpg" download>{t("sampleCertificate")}</a>
                  <span className="block text-sm text-ink-2">{t("sampleCertificateNote")}</span>
                </li>
                <li>
                  <a href="/demo/sample-dog.jpg" download>{t("sampleDog")}</a>
                  <span className="block text-sm text-ink-2">{t("sampleDogCredit")}</span>
                </li>
              </ul>
            </section>
          </div>
        </details>

        <Notice tone="pending" title={t("limitsTitle")}>
          <ul className="list-disc space-y-1 pl-5">
            <li>{t("limits.reminders")}</li>
            <li>{t("limits.matching")}</li>
            <li>{t("limits.offline")}</li>
            <li>{t("limits.language")}</li>
            <li>{t("limits.reset")}</li>
          </ul>
        </Notice>
      </section>
    </PublicPage>
  );
}
