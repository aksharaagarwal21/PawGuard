import { Dog, HeartPulse, Stethoscope, Users } from "lucide-react";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Notice } from "@pawguard/ui";

import { Faq } from "@/components/landing/faq";
import { StatusGuide } from "@/components/landing/status-guide";
import { PublicPage } from "@/components/public-shell";
import { Link } from "@/i18n/navigation";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "guide" });
  return { title: t("title") };
}

const ROLES = [
  { key: "owner", Icon: Dog },
  { key: "vet", Icon: Stethoscope },
  { key: "manager", Icon: Stethoscope },
  { key: "volunteer", Icon: Users },
] as const;

/** "How to use PawGuard": short sections per role, the status guide and the FAQ. */
export default async function GuidePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("guide");
  return (
    <PublicPage locale={locale}>
      <div className="container-pg max-w-4xl space-y-12 py-10 md:py-14">
        <header className="space-y-3">
          <h1 className="text-3xl md:text-4xl">{t("title")}</h1>
          <p className="max-w-prose text-lg text-ink-2">{t("intro")}</p>
          <nav aria-label={t("contents")}>
            <ul className="flex flex-wrap gap-2 text-sm">
              {(["roles", "colours", "questions"] as const).map((k) => (
                <li key={k}>
                  <a href={`#${k}`} className="inline-flex min-h-11 items-center rounded-full border border-control bg-surface px-4 font-semibold no-underline hover:bg-sage">
                    {t(`toc.${k}`)}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </header>

        <Notice tone="urgent" title={t("biteTitle")}>
          <p>
            <Link href="/help" className="inline-flex items-center gap-1.5 font-semibold text-urgent">
              <HeartPulse aria-hidden className="size-4" />
              {t("biteLink")}
            </Link>
          </p>
        </Notice>

        <section id="roles" aria-labelledby="roles-h" className="scroll-mt-4 space-y-5">
          <h2 id="roles-h" className="text-2xl">{t("rolesTitle")}</h2>
          <div className="grid gap-4 md:grid-cols-2">
            {ROLES.map(({ key, Icon }) => (
              <section key={key} aria-labelledby={`role-${key}`} className="rounded-card border border-divider bg-surface p-5">
                <h3 id={`role-${key}`} className="flex items-center gap-2 text-lg">
                  <span className="flex size-9 items-center justify-center rounded-full bg-sage text-primary">
                    <Icon aria-hidden className="size-4" />
                  </span>
                  {t(`roles.${key}.title`)}
                </h3>
                <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-ink-2">
                  {(["one", "two", "three"] as const).map((s) => (
                    <li key={s}>{t(`roles.${key}.${s}`)}</li>
                  ))}
                </ol>
              </section>
            ))}
          </div>
          <p className="text-sm text-ink-2">{t("tourHint")}</p>
        </section>

        <section id="colours" aria-labelledby="colours-h" className="scroll-mt-4 space-y-4">
          <h2 id="colours-h" className="text-2xl">{t("coloursTitle")}</h2>
          <StatusGuide />
        </section>

        <section id="questions" aria-labelledby="faq-h" className="scroll-mt-4 space-y-4">
          <h2 id="faq-h" className="text-2xl">{t("faqTitle")}</h2>
          <Faq />
        </section>
      </div>
    </PublicPage>
  );
}
