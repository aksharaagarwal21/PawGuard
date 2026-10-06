import { ClipboardCheck, Search, ShieldQuestion } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button } from "@pawguard/ui";

import { PublicPage } from "@/components/public-shell";
import { Link } from "@/i18n/navigation";

export default async function LandingPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("landing");
  const steps = [
    { key: "one", Icon: Search, bg: "bg-sage" },
    { key: "two", Icon: ClipboardCheck, bg: "bg-sky" },
    { key: "three", Icon: ShieldQuestion, bg: "bg-lavender" },
  ] as const;
  return (
    <PublicPage locale={locale}>
      <section className="container-pg grid items-center gap-10 py-12 md:grid-cols-[1.15fr_0.85fr] md:py-20">
        <div>
          <h1 className="text-3xl md:text-[2.875rem] md:leading-[1.12]">{t("headline")}</h1>
          <p className="prose-pg mt-5 text-lg text-ink-2">{t("subheading")}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild variant="urgent">
              <Link href="/help">{t("primaryAction")}</Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <a href="#prevention">{t("secondaryAction")}</a>
            </Button>
          </div>
        </div>
        <HeroIllustration />
      </section>

      <section id="prevention" className="bg-surface py-14">
        <div className="container-pg">
          <h2 className="text-2xl">{t("howTitle")}</h2>
          <ol className="mt-8 grid gap-6 md:grid-cols-3">
            {steps.map(({ key, Icon, bg }, i) => (
              <li key={key} className="rounded-card border border-divider p-6">
                <span className={`flex size-11 items-center justify-center rounded-full ${bg} text-primary`}>
                  <Icon aria-hidden className="size-5" />
                </span>
                <h3 className="mt-4 text-lg">
                  <span className="text-ink-2">{i + 1}. </span>
                  {t(`steps.${key}.title`)}
                </h3>
                <p className="mt-2 text-ink-2">{t(`steps.${key}.body`)}</p>
              </li>
            ))}
          </ol>
          <p className="mt-6 text-sm text-ink-2">{t("releaseNote")}</p>
        </div>
      </section>

      <section className="container-pg py-14">
        <div className="rounded-card bg-sand p-6 md:p-8">
          <h2 className="text-xl">{t("transparencyTitle")}</h2>
          <ul className="prose-pg mt-4 list-disc space-y-2 pl-5">
            <li>{t("transparency.one")}</li>
            <li>{t("transparency.two")}</li>
            <li>{t("transparency.three")}</li>
          </ul>
        </div>
      </section>
    </PublicPage>
  );
}

/** Decorative, generated illustration — not a photograph of any real animal or person. */
function HeroIllustration() {
  return (
    <svg aria-hidden viewBox="0 0 420 340" className="mx-auto w-full max-w-md">
      <rect x="10" y="20" width="400" height="300" rx="28" fill="#E8F1E9" />
      <circle cx="345" cy="78" r="30" fill="#FBF1DE" />
      <path d="M10 250 Q120 200 210 240 T410 230 V292 a28 28 0 0 1 -28 28 H38 a28 28 0 0 1 -28 -28Z" fill="#CBD8CE" />
      <g transform="translate(205 118)">
        <ellipse cx="72" cy="168" rx="86" ry="10" fill="#203A34" opacity="0.08" />
        <path d="M116 132 q34 -6 30 -40" stroke="#A97C4E" strokeWidth="10" fill="none" strokeLinecap="round" />
        <ellipse cx="74" cy="124" rx="48" ry="44" fill="#B88A5A" />
        <rect x="48" y="128" width="15" height="38" rx="7" fill="#A97C4E" />
        <rect x="84" y="128" width="15" height="38" rx="7" fill="#A97C4E" />
        <ellipse cx="38" cy="44" rx="13" ry="25" transform="rotate(18 38 44)" fill="#8E6440" />
        <ellipse cx="106" cy="44" rx="13" ry="25" transform="rotate(-18 106 44)" fill="#8E6440" />
        <circle cx="72" cy="54" r="36" fill="#B88A5A" />
        <ellipse cx="72" cy="72" rx="19" ry="14" fill="#E2C49E" />
        <ellipse cx="72" cy="64" rx="6.5" ry="4.5" fill="#203A34" />
        <circle cx="58" cy="47" r="4.2" fill="#203A34" />
        <circle cx="86" cy="47" r="4.2" fill="#203A34" />
        <rect x="47" y="88" width="50" height="8" rx="4" fill="#205C4F" />
        <circle cx="72" cy="101" r="5" fill="#FBF1DE" stroke="#205C4F" strokeWidth="1.5" />
      </g>
      <g transform="translate(40 60)">
        <rect width="120" height="76" rx="12" fill="#FFFFFF" />
        <rect x="14" y="16" width="54" height="8" rx="4" fill="#576E64" opacity="0.5" />
        <rect x="14" y="32" width="88" height="8" rx="4" fill="#576E64" opacity="0.3" />
        <rect x="14" y="50" width="46" height="14" rx="7" fill="#E8F1E9" />
        <path d="M22 57 l4 4 l8 -8" stroke="#205C4F" strokeWidth="2.5" fill="none" strokeLinecap="round" />
      </g>
    </svg>
  );
}
