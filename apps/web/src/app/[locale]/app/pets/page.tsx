import { Plus } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button, Notice, StatusChip } from "@pawguard/ui";

import { PageBody } from "@/components/page-header";
import { NextStepCard, dueWords, pickNextStep } from "@/components/pets/next-step";
import { PetAvatar, PetStatusChip } from "@/components/pets/status";
import { WelcomeTour } from "@/components/tour/welcome-tour";
import { Link } from "@/i18n/navigation";
import { pageContext } from "@/lib/page-context";

const OWNER_TOUR = [
  { target: '[data-tour="pets"]', key: "pets" },
  { target: '[data-tour="bell"]', key: "bell" },
  { target: '[data-tour="next-step"]', key: "next" },
  { target: '[data-tour="pets"] li:first-child', key: "card" },
];

function greetingKey(tz: string): "morning" | "afternoon" | "evening" {
  const hour = Number(new Intl.DateTimeFormat("en-GB", { hour: "numeric", hourCycle: "h23", timeZone: tz }).format(new Date()));
  return hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening";
}

/** "My pets": greeting, a one-line summary, the single next step, then each pet with its status in words. */
export default async function MyPetsPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  const t = await getTranslations("pets");
  const tn = await getTranslations("pets.next");
  const { data, error } = await ctx.api.GET("/api/v1/my/pets");
  const pets = data ?? [];
  const count = (s: string) => pets.filter((p) => p.status.status === s).length;
  const name = ctx.me.preferred_name;
  const summary = [
    count("overdue") ? t("summary.attention", { count: count("overdue") }) : null,
    count("due_soon") ? t("summary.soon", { count: count("due_soon") }) : null,
    count("up_to_date") ? t("summary.upToDate", { count: count("up_to_date") }) : null,
    count("unverified_record") ? t("summary.waiting", { count: count("unverified_record") }) : null,
    count("no_verified_record") ? t("summary.none", { count: count("no_verified_record") }) : null,
  ].filter(Boolean);

  return (
    <PageBody>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-ink-2">{name ? t(`greeting.${greetingKey(ctx.tz)}`, { name }) : t("greetingNoName")}</p>
          <h1 className="text-2xl">{t("title")}</h1>
          {summary.length ? <p className="mt-1 font-semibold">{summary.join(" · ")}</p> : null}
        </div>
        <Button asChild variant="secondary">
          <Link href="/app/pets/new">
            <Plus aria-hidden className="size-5" />
            {t("addPet")}
          </Link>
        </Button>
      </div>

      {error ? <Notice tone="urgent">{t("loadFailed")}</Notice> : null}

      {pets.length === 0 && !error ? (
        <div className="rounded-card border border-dashed border-control bg-surface p-8 text-center">
          <EmptyIllustration />
          <h2 className="mt-4 text-xl">{t("emptyTitle")}</h2>
          <p className="mx-auto mt-2 max-w-prose text-ink-2">{t("emptyBody")}</p>
          <Button asChild size="lg" className="mt-5">
            <Link href="/app/pets/new">{t("addPet")}</Link>
          </Button>
        </div>
      ) : (
        <>
          <NextStepCard step={pickNextStep(pets, tn)} label={tn("label")} />
          <ul className="grid gap-3 md:grid-cols-2" aria-label={t("listLabel")} data-tour="pets">
            {pets.map((p) => {
              const words = dueWords(p.status.days_until_due, tn);
              return (
                <li key={p.id}>
                  <Link
                    href={`/app/pets/${p.id}`}
                    className="flex h-full gap-4 rounded-card border border-divider bg-surface p-4 text-ink no-underline shadow-card hover:border-control hover:bg-sage/30 motion-safe:transition-colors motion-safe:duration-150"
                  >
                      <PetAvatar url={p.photo_url} name={p.name} />
                      <div className="min-w-0 flex-1 space-y-1.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-display text-lg font-semibold">{p.name}</span>
                          {p.is_demo ? <StatusChip kind="demo">{t("demoData")}</StatusChip> : null}
                        </div>
                        <PetStatusChip status={p.status} />
                        <p className="text-sm">
                          {words ? (
                            <>
                              <span className={p.status.status === "overdue" ? "font-semibold text-urgent" : "font-semibold"}>
                                {words}
                              </span>
                              {p.status.vaccine ? <span className="text-ink-2"> · {p.status.vaccine}</span> : null}
                            </>
                          ) : (
                            <span className="text-ink-2">{t(`statusShort.${p.status.status}`)}</span>
                          )}
                        </p>
                        <p className="text-sm text-ink-2">
                          {t(`species.${p.species as "dog" | "cat"}`)} · {p.clinic_name}
                        </p>
                        {p.awaiting_verification > 0 ? (
                          <p className="text-sm text-ink-2">{t("awaiting", { count: p.awaiting_verification })}</p>
                        ) : null}
                      </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        </>
      )}
      <p className="text-sm text-ink-2">{t("remindOnly")}</p>
      {pets.length > 0 ? <WelcomeTour id="owner" steps={OWNER_TOUR} /> : null}
    </PageBody>
  );
}

/** Simple original drawing: a paw print inside a card. Decorative. */
function EmptyIllustration() {
  return (
    <svg aria-hidden viewBox="0 0 120 90" className="mx-auto h-24 w-auto">
      <rect x="10" y="10" width="100" height="70" rx="12" fill="#E8F1E9" />
      <rect x="22" y="22" width="40" height="6" rx="3" fill="#CBD8CE" />
      <rect x="22" y="34" width="56" height="6" rx="3" fill="#CBD8CE" />
      <g fill="#205C4F" transform="translate(76 46)">
        <ellipse cx="10" cy="14" rx="8" ry="7" />
        <circle cx="2" cy="4" r="3.2" />
        <circle cx="8" cy="0" r="3.2" />
        <circle cx="14" cy="0" r="3.2" />
        <circle cx="19.5" cy="4.5" r="3.2" />
      </g>
    </svg>
  );
}
