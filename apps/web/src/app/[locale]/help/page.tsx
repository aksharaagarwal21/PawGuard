import { Droplets, Hospital, Phone } from "lucide-react";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Notice } from "@pawguard/ui";

import { PublicPage } from "@/components/public-shell";
import { PUBLIC_SOURCES } from "@/content/public-sources";
import { Link } from "@/i18n/navigation";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "help" });
  return { title: t("title") };
}

/**
 * Urgent guidance. Rendered on the server with no account, no form, no AI, no images required.
 * Health wording is not machine-translated: non-English locales show the English text with a notice until
 * reviewed translations exist (docs/CONTENT_REGISTER.md).
 */
export default async function HelpPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("help");
  const tc = await getTranslations("common");
  return (
    <PublicPage locale={locale}>
      <article className="container-pg py-10" lang="en">
        {locale !== "en" ? (
          <Notice tone="info" className="mb-6" lang={locale}>
            {tc("untranslatedNotice")}
          </Notice>
        ) : null}
        <h1 className="text-3xl">{t("title")}</h1>
        <p className="prose-pg mt-3 text-lg">{t("intro")}</p>

        <ol className="mt-8 grid gap-4 md:grid-cols-2">
          <li className="rounded-card border-l-4 border-urgent bg-surface p-6 shadow-card">
            <Droplets aria-hidden className="size-7 text-urgent" />
            <h2 className="mt-3 text-xl">{t("stepWashTitle")}</h2>
            <p className="mt-2 text-lg">{t("stepWashBody")}</p>
          </li>
          <li className="rounded-card border-l-4 border-urgent bg-surface p-6 shadow-card">
            <Hospital aria-hidden className="size-7 text-urgent" />
            <h2 className="mt-3 text-xl">{t("stepCareTitle")}</h2>
            <p className="mt-2 text-lg">{t("stepCareBody")}</p>
          </li>
        </ol>

        <section className="mt-8 rounded-card bg-surface p-6">
          <h2 className="flex items-center gap-2 text-xl">
            <Phone aria-hidden className="size-5 text-primary" />
            {t("callTitle")}
          </h2>
          <ul className="prose-pg mt-3 space-y-3">
            <li>
              <a href="tel:112" className="font-display text-xl font-bold">
                112
              </a>{" "}
              <span className="text-ink-2">— {t("call112")}</span>
            </li>
            <li>
              <a href="tel:15400" className="font-display text-xl font-bold">
                15400
              </a>{" "}
              <span className="text-ink-2">— {t("call15400")}</span>
            </li>
          </ul>
          <p className="mt-4">
            <Link href="/find-care">{t("findCareLink")}</Link>
          </p>
        </section>

        <section className="prose-pg mt-8">
          <h2 className="text-xl">{t("whyTitle")}</h2>
          <p className="mt-2">{t("whyBody")}</p>
          <h2 className="mt-6 text-xl">{t("notDoTitle")}</h2>
          <p className="mt-2">{t("notDoBody")}</p>
        </section>

        <aside className="mt-10 space-y-4">
          <Notice tone="pending" title={tc("reviewStatus.unreviewed")}>
            {t("reviewNotice")}
          </Notice>
          <div>
            <h2 className="text-base">{t("sourcesTitle")}</h2>
            <ul className="mt-2 space-y-1 text-sm text-ink-2">
              {PUBLIC_SOURCES.map((s) => (
                <li key={s.id}>
                  <a href={s.url} rel="noopener noreferrer" target="_blank">
                    {s.publisher}: {s.title}
                  </a>{" "}
                  — {tc("checked", { date: s.checked })}
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </article>
    </PublicPage>
  );
}
