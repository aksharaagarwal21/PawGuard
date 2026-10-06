import {
  BellRing,
  Camera,
  ClipboardCheck,
  Dog,
  ExternalLink,
  LockKeyhole,
  QrCode,
  ShieldCheck,
  Stethoscope,
  Tag,
  Users,
} from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button, StatusChip } from "@pawguard/ui";

import { Faq } from "@/components/landing/faq";
import { StatusGuide } from "@/components/landing/status-guide";
import { PetStatusChip } from "@/components/pets/status";
import { PublicPage } from "@/components/public-shell";
import { Link } from "@/i18n/navigation";
import { serverEnv } from "@/lib/server-env";

const STEPS = [
  { key: "add", Icon: Camera },
  { key: "vet", Icon: Stethoscope },
  { key: "remind", Icon: BellRing },
  { key: "card", Icon: QrCode },
] as const;

const AUDIENCES = [
  { key: "owners", Icon: Dog, bg: "bg-sage", id: "for-owners" },
  { key: "clinics", Icon: Stethoscope, bg: "bg-sky", id: "for-clinics" },
  { key: "volunteers", Icon: Users, bg: "bg-lavender", id: "for-volunteers" },
] as const;

const TRUST = [
  { key: "vets", Icon: ShieldCheck },
  { key: "contact", Icon: LockKeyhole },
  { key: "reminds", Icon: Stethoscope },
  { key: "demo", Icon: Tag },
] as const;

const WHO_URL = "https://www.who.int/news-room/fact-sheets/detail/rabies";

/** Public landing page, told as a short story: what it is, how it works, what the colours mean, who it's for. */
export default async function LandingPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("landing");
  const getStarted = serverEnv().demoMode ? "/welcome" : "/sign-in";
  return (
    <PublicPage locale={locale}>
      {/* Hero */}
      <section className="container-pg grid items-center gap-10 py-12 md:py-16 lg:grid-cols-[1.1fr_0.9fr]">
        <div>
          <h1 className="text-3xl md:text-[2.875rem] md:leading-[1.12]">{t("headline")}</h1>
          <p className="prose-pg mt-5 text-lg text-ink-2">{t("subheading")}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href={getStarted}>{t("getStarted")}</Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <a href="#how">{t("seeHow")}</a>
            </Button>
          </div>
        </div>
        <PreviewCard />
      </section>

      {/* How it works */}
      <section id="how" aria-labelledby="how-h" className="scroll-mt-4 bg-surface py-14">
        <div className="container-pg">
          <h2 id="how-h" className="text-2xl">{t("howTitle")}</h2>
          <p className="mt-2 max-w-prose text-ink-2">{t("howIntro")}</p>
          <ol className="relative mt-10 grid gap-8 lg:grid-cols-4 lg:gap-6">
            {/* Thin connecting line: vertical on phones, horizontal on wide screens. */}
            <span aria-hidden className="absolute top-5 right-[12.5%] left-[12.5%] hidden h-0.5 bg-divider lg:block" />
            {STEPS.map(({ key, Icon }, i) => (
              <li key={key} className="relative flex gap-4 lg:flex-col lg:items-center lg:text-center">
                {i < STEPS.length - 1 ? (
                  <span aria-hidden className="absolute top-10 -bottom-8 left-5 w-0.5 -translate-x-1/2 bg-divider lg:hidden" />
                ) : null}
                <span className="relative z-10 flex size-10 shrink-0 items-center justify-center rounded-full bg-primary font-display font-bold text-white ring-4 ring-surface">
                  {i + 1}
                </span>
                <div>
                  <h3 className="text-lg">
                    <Icon aria-hidden className="mr-1.5 inline size-5 align-[-3px] text-primary" />
                    {t(`steps.${key}.title`)}
                  </h3>
                  <p className="mt-1 text-ink-2">{t(`steps.${key}.body`)}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* What the colours mean */}
      <section aria-labelledby="colours-h" className="container-pg py-14">
        <h2 id="colours-h" className="text-2xl">{t("coloursTitle")}</h2>
        <p className="mt-2 max-w-prose text-ink-2">{t("coloursIntro")}</p>
        <div className="mt-6 max-w-3xl">
          <StatusGuide />
        </div>
      </section>

      {/* Who it's for */}
      <section aria-labelledby="who-h" className="bg-surface py-14">
        <div className="container-pg">
          <h2 id="who-h" className="text-2xl">{t("whoTitle")}</h2>
          <ul className="mt-8 grid gap-5 md:grid-cols-3">
            {AUDIENCES.map(({ key, Icon, bg, id }) => (
              <li key={key} id={id} className="scroll-mt-4 rounded-card border border-divider p-6">
                <span className={`flex size-11 items-center justify-center rounded-full ${bg} text-primary`}>
                  <Icon aria-hidden className="size-5" />
                </span>
                <h3 className="mt-4 text-lg">{t(`who.${key}.title`)}</h3>
                <ul className="mt-3 list-disc space-y-1.5 pl-5 text-ink-2">
                  {(["one", "two", "three"] as const).map((b) => (
                    <li key={b}>{t(`who.${key}.${b}`)}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Why you can trust it */}
      <section aria-labelledby="trust-h" className="container-pg py-14">
        <h2 id="trust-h" className="text-2xl">{t("trustTitle")}</h2>
        <ul className="mt-6 grid gap-4 sm:grid-cols-2">
          {TRUST.map(({ key, Icon }) => (
            <li key={key} className="flex gap-3 rounded-card bg-sage p-4">
              <Icon aria-hidden className="mt-0.5 size-5 shrink-0 text-primary" />
              <p>{t(`trust.${key}`)}</p>
            </li>
          ))}
        </ul>
      </section>

      {/* Why it matters: quoted, attributed facts only */}
      <section aria-labelledby="matters-h" className="bg-sand py-14">
        <div className="container-pg">
          <h2 id="matters-h" className="text-2xl">{t("mattersTitle")}</h2>
          <p className="mt-2 max-w-prose">{t("mattersIntro")}</p>
          <ul className="mt-6 grid gap-4 md:grid-cols-3" lang="en">
            {(["preventable", "dogs", "vaccinating"] as const).map((k) => (
              <li key={k} className="rounded-card bg-surface p-5">
                <blockquote cite={WHO_URL}>
                  <p>“{t(`matters.${k}`)}”</p>
                </blockquote>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-sm">
            {t("mattersSource")}{" "}
            <a href={WHO_URL} target="_blank" rel="noopener noreferrer">
              {t("mattersSourceLink")}
              <ExternalLink aria-hidden className="ml-1 inline size-3.5" />
            </a>{" "}
            · {t("mattersChecked")}
          </p>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" aria-labelledby="faq-h" className="container-pg scroll-mt-4 py-14">
        <h2 id="faq-h" className="text-2xl">{t("faqTitle")}</h2>
        <div className="mt-6 max-w-3xl">
          <Faq />
        </div>
        <div className="mt-10 flex flex-wrap items-center gap-3">
          <Button asChild size="lg">
            <Link href={getStarted}>{t("getStarted")}</Link>
          </Button>
          <p className="text-ink-2">{t("closing")}</p>
        </div>
      </section>
    </PublicPage>
  );
}

/** Product preview: what "My pets" looks like (fictional pets). Not a statistic and not real data. */
async function PreviewCard() {
  const t = await getTranslations("landing.preview");
  const pets = [
    { name: "Bruno", kind: "dog", status: "up_to_date", line: t("brunoLine") },
    { name: "Misty", kind: "cat", status: "due_soon", line: t("mistyLine") },
    { name: "Coco", kind: "dog", status: "overdue", line: t("cocoLine") },
  ] as const;
  return (
    <figure className="mx-auto w-full max-w-md">
      <div className="rounded-card border border-divider bg-surface p-5 shadow-card">
        <div className="flex items-center justify-between gap-2">
          <p className="font-display text-lg font-semibold">{t("title")}</p>
          <StatusChip kind="demo">{t("example")}</StatusChip>
        </div>
        <ul className="mt-4 space-y-3">
          {pets.map((p) => (
            <li key={p.name} className="flex flex-wrap items-center gap-3 rounded-control border border-divider p-3">
              <span aria-hidden className="flex size-11 shrink-0 items-center justify-center rounded-full bg-sage text-primary">
                <Dog className="size-5" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-display font-semibold">
                  {p.name} <span className="text-sm font-normal text-ink-2">· {t(p.kind)}</span>
                </p>
                <p className="text-sm text-ink-2">{p.line}</p>
              </div>
              <PetStatusChip status={{ status: p.status }} />
            </li>
          ))}
        </ul>
        <div className="mt-4 flex items-center gap-2 rounded-control bg-sand p-3 text-sm">
          <ClipboardCheck aria-hidden className="size-4 shrink-0 text-primary" />
          <span>{t("nextStep")}</span>
        </div>
      </div>
      <figcaption className="mt-2 text-center text-sm text-ink-2">{t("caption")}</figcaption>
    </figure>
  );
}
