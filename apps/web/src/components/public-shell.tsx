import { HeartPulse } from "lucide-react";
import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/navigation";
import { serverEnv } from "@/lib/server-env";

import { LanguageSwitcher } from "./language-switcher";
import { Wordmark } from "./wordmark";

export async function PublicHeader() {
  const t = await getTranslations("nav");
  return (
    <header className="border-b border-divider bg-canvas">
      <div className="container-pg flex flex-wrap items-center gap-x-6 gap-y-2 py-3">
        <Link href="/" className="no-underline">
          <Wordmark />
        </Link>
        <nav aria-label={t("mainNavigation")} className="order-3 w-full sm:order-none sm:w-auto">
          <ul className="flex flex-wrap gap-x-1 text-sm">
            {(
              [
                ["/learn", t("learn")],
                ["/find-care", t("findCare")],
                ["/about", t("about")],
              ] as const
            ).map(([href, label]) => (
              <li key={href}>
                <Link
                  href={href}
                  className="inline-flex min-h-11 items-center rounded-control px-3 font-display font-semibold text-ink no-underline hover:bg-sage"
                >
                  {label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <LanguageSwitcher />
          <Link
            href="/sign-in"
            className="inline-flex min-h-11 items-center rounded-control border border-control bg-surface px-3 font-display text-sm font-semibold text-ink no-underline hover:bg-sage"
          >
            {t("teamSignIn")}
          </Link>
        </div>
      </div>
      <div className="bg-urgent-soft">
        <div className="container-pg py-2">
          <Link href="/help" className="inline-flex min-h-11 items-center gap-2 font-display font-bold text-urgent">
            <HeartPulse aria-hidden className="size-5" />
            {t("getHelp")}
          </Link>
        </div>
      </div>
    </header>
  );
}

export async function DemoBanner() {
  if (!serverEnv().demoMode) return null;
  const t = await getTranslations("common");
  return (
    <div role="note" className="bg-lavender text-ink">
      <p className="container-pg py-2 text-sm font-semibold">{t("demoBanner")}</p>
    </div>
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
  return (
    <footer className="mt-16 border-t border-divider bg-surface">
      <div className="container-pg flex flex-wrap items-center justify-between gap-4 py-8 text-sm text-ink-2">
        <p>{tm("siteName")}</p>
        <ul className="flex flex-wrap gap-4">
          <li>
            <Link href="/sources">{t("sources")}</Link>
          </li>
          <li>
            <Link href="/about">{t("about")}</Link>
          </li>
        </ul>
      </div>
    </footer>
  );
}

export async function PublicPage({ locale, children }: { locale: string; children: React.ReactNode }) {
  return (
    <>
      <DemoBanner />
      <TranslationNotice locale={locale} />
      <PublicHeader />
      <main id="main" tabIndex={-1} className="outline-none">
        {children}
      </main>
      <PublicFooter />
    </>
  );
}
