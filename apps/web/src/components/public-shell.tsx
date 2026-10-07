import { HeartPulse } from "lucide-react";
import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/navigation";
import { serverEnv } from "@/lib/server-env";

import { LanguageSwitcher } from "./language-switcher";
import { Wordmark } from "./wordmark";

export async function PublicHeader() {
  const t = await getTranslations("nav");
  const tm = await getTranslations("meta");
  const getStarted = "/sign-in";
  const navLink =
    "inline-flex min-h-11 items-center rounded-control px-3 font-display font-semibold text-ink no-underline hover:bg-sage motion-safe:transition-colors motion-safe:duration-150";
  return (
    <header className="border-b border-divider bg-canvas">
      <div className="container-pg flex flex-wrap items-center gap-x-4 gap-y-1 pt-3 pb-1">
        <Link href="/" className="no-underline" aria-label={tm("siteName")}>
          <span className="sm:hidden">
            <Wordmark compact />
          </span>
          <span className="hidden sm:inline">
            <Wordmark />
          </span>
        </Link>
        <nav aria-label={t("mainNavigation")} className="order-3 lg:order-none">
          <ul className="-ml-3 flex flex-wrap text-sm">
            <li>
              <Link href="/#how" className={navLink}>
                {t("howItWorks")}
              </Link>
            </li>
            <li>
              <Link href="/#for-clinics" className={navLink}>
                {t("forClinics")}
              </Link>
            </li>
            <li>
              <Link href="/guide" className={navLink}>
                {t("helpGuide")}
              </Link>
            </li>
            <li>
              <Link href="/verify" className={navLink}>
                {t("verifyCertificate")}
              </Link>
            </li>
          </ul>
        </nav>
        <div className="order-4 ml-auto lg:order-none">
          <LanguageSwitcher />
        </div>
        <div className="ml-auto flex items-center gap-2 lg:ml-0">
          <Link
            href="/sign-in"
            className="inline-flex min-h-11 items-center rounded-control border border-control bg-surface px-3 font-display text-sm font-semibold text-ink no-underline hover:bg-sage"
          >
            {t("signIn")}
          </Link>
          <Link
            href={getStarted}
            className="inline-flex min-h-11 items-center rounded-control bg-primary px-4 font-display text-sm font-semibold text-white no-underline hover:bg-primary-hover"
          >
            {t("getStarted")}
          </Link>
        </div>
      </div>
      <div className="container-pg pb-2">
        <Link href="/help" className="inline-flex min-h-11 items-center gap-1.5 text-sm font-semibold text-urgent">
          <HeartPulse aria-hidden className="size-4" />
          {t("biteHelpShort")}
        </Link>
      </div>
    </header>
  );
}

export async function TranslationNotice({ locale }: { locale: string }) {
  if (locale === "en") return null;
  const t = await getTranslations("common");
  return (
    <div className="bg-sky">
      <p className="container-pg py-1.5 text-sm">{t("translationDraftNotice")}</p>
    </div>
  );
}

export async function PublicFooter() {
  const t = await getTranslations("nav");
  const tm = await getTranslations("meta");
  const tf = await getTranslations("footer");
  return (
    <footer className="mt-16 border-t border-divider bg-surface">
      <div className="container-pg grid gap-6 py-8 text-sm text-ink-2 md:grid-cols-[1fr_auto] md:items-start">
        <div className="space-y-2">
          <p className="font-display font-semibold text-ink">{tm("siteName")}</p>
          {serverEnv().demoMode ? <p className="font-semibold">{tf("demoVersion")}</p> : null}
          <p>{tf("credit")}</p>
        </div>
        <ul className="flex flex-wrap gap-x-5 gap-y-2">
          <li>
            <Link href="/help" className="font-semibold text-urgent">
              {t("getHelp")}
            </Link>
          </li>
          <li>
            <Link href="/about">{t("about")}</Link>
          </li>
          <li>
            <Link href="/sources">{t("sources")}</Link>
          </li>
          <li>
            <Link href="/verify">{t("verifyCertificate")}</Link>
          </li>
        </ul>
      </div>
    </footer>
  );
}

export async function PublicPage({ locale, children }: { locale: string; children: React.ReactNode }) {
  return (
    <>
      <TranslationNotice locale={locale} />
      <PublicHeader />
      <main id="main" tabIndex={-1} className="outline-none">
        {children}
      </main>
      <PublicFooter />
    </>
  );
}
