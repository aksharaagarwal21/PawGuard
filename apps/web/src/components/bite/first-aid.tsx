import { Droplets, Hospital, Phone, Stethoscope, XCircle } from "lucide-react";
import { getLocale, getTranslations } from "next-intl/server";

/** First aid, always the first thing on every bite page. Wording: WHO + India's NRCP (CONTENT_REGISTER C-BITE-01..03),
 *  pending clinical review. Tamil/Hindi are draft translations and say so. */
export async function FirstAid({ headingLevel = 2 }: { headingLevel?: 1 | 2 | 3 }) {
  const t = await getTranslations("bite.firstAid");
  const tb = await getTranslations("bite");
  const locale = await getLocale();
  const H = headingLevel === 1 ? "h1" : headingLevel === 3 ? "h3" : "h2";
  return (
    <section aria-labelledby="first-aid-h" className="space-y-4 rounded-card border-l-8 border-urgent bg-urgent-soft p-5" data-testid="first-aid">
      <H id="first-aid-h" className="text-2xl text-urgent">
        {t("title")}
      </H>
      <ol className="space-y-3 text-lg">
        <li className="flex gap-3">
          <Droplets aria-hidden className="mt-1 size-6 shrink-0 text-urgent" />
          <span className="font-semibold">{t("wash")}</span>
        </li>
        <li className="flex gap-3">
          <Stethoscope aria-hidden className="mt-1 size-6 shrink-0 text-urgent" />
          <span className="font-semibold">{t("doctor")}</span>
        </li>
        <li className="flex gap-3">
          <XCircle aria-hidden className="mt-1 size-6 shrink-0 text-urgent" />
          <span>{t("noRemedies")}</span>
        </li>
      </ol>
      <div className="grid gap-2 sm:grid-cols-2">
        <a
          href="tel:112"
          className="inline-flex min-h-12 items-center justify-center gap-2 rounded-control bg-urgent px-4 font-display text-lg font-semibold text-white no-underline"
        >
          <Phone aria-hidden className="size-5" />
          {t("call")}
        </a>
        <a
          href={`/${locale}/find-care`}
          className="inline-flex min-h-12 items-center justify-center gap-2 rounded-control border-2 border-urgent bg-surface px-4 font-display font-semibold text-urgent no-underline"
        >
          <Hospital aria-hidden className="size-5" />
          {t("findCare")}
        </a>
      </div>
      <p className="text-xs text-ink-2">{t("source")}</p>
      {locale !== "en" ? <p className="text-xs font-semibold">{tb("draftTranslation")}</p> : null}
    </section>
  );
}
