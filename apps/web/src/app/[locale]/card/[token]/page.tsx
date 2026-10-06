import type { Schemas } from "@pawguard/api-client";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Card, Notice, StatusChip } from "@pawguard/ui";

import { FinderStartForm } from "@/components/lost/lost-forms";
import { NextDueLine, PetAvatar, PetStatusChip } from "@/components/pets/status";
import { PublicPage } from "@/components/public-shell";
import { formatPartialDate } from "@/lib/format";
import { serverEnv } from "@/lib/server-env";

export const metadata: Metadata = { robots: { index: false, follow: false } };

async function loadLost(token: string): Promise<Schemas["LostStatusOut"] | null> {
  try {
    const r = await fetch(new URL(`/api/v1/public/cards/${token}/lost`, serverEnv().PAWGUARD_API_INTERNAL_URL), {
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    return r.ok ? ((await r.json()) as Schemas["LostStatusOut"]) : null;
  } catch {
    return null;
  }
}

async function load(token: string): Promise<Schemas["PublicCardOut"] | null> {
  if (!/^[A-Za-z0-9_-]{32,100}$/.test(token)) return null;
  try {
    const r = await fetch(new URL(`/api/v1/public/cards/${token}`, serverEnv().PAWGUARD_API_INTERNAL_URL), {
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    return r.ok ? ((await r.json()) as Schemas["PublicCardOut"]) : null;
  } catch {
    return null;
  }
}

/** Public vaccination card behind a pet's QR code: verified vaccinations only, nothing about the owner. */
export default async function PublicCardPage({ params }: { params: Promise<{ locale: string; token: string }> }) {
  const { locale, token } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("publicCard");
  const tp = await getTranslations("pets");
  const tc = await getTranslations("common");
  const card = await load(token);
  const lost = card ? await loadLost(token) : null;
  const tl = await getTranslations("lost.finder");
  const fmt = (d: string | null | undefined) => formatPartialDate(d, "day", locale, tc("notRecorded"));
  return (
    <PublicPage locale={locale}>
      <div className="container-pg max-w-2xl space-y-5 py-8">
        {!card ? (
          <Notice tone="neutral" title={t("notFoundTitle")}>
            <p>{t("notFoundBody")}</p>
          </Notice>
        ) : (
          <>
            <h1 className="sr-only">{t("title", { name: card.pet_name })}</h1>
            {lost?.lost ? (
              <section aria-labelledby="lost-h" className="space-y-3 rounded-card border-2 border-urgent bg-urgent-soft p-5">
                <h2 id="lost-h" className="text-xl text-urgent">{tl("bannerTitle", { name: card.pet_name })}</h2>
                <p>
                  {tl("bannerBody", {
                    date: lost.last_seen_on ? formatPartialDate(lost.last_seen_on, "day", locale, "") : tl("recently"),
                    area: lost.area_text ?? tl("unknownArea"),
                  })}
                </p>
                <FinderStartForm cardToken={token} />
              </section>
            ) : null}
            <Card className="space-y-4">
              <div className="flex items-start gap-4">
                <PetAvatar url={card.photo_url} name={card.pet_name} size="lg" />
                <div className="min-w-0 space-y-1.5">
                  <p className="font-display text-2xl font-semibold" aria-hidden>
                    {card.pet_name}
                  </p>
                  <p className="text-sm text-ink-2">
                    {tp(`species.${card.species as "dog" | "cat"}`)} · {card.clinic_name}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <PetStatusChip status={card.status} />
                    {card.is_demo ? <StatusChip kind="demo">{tp("demoData")}</StatusChip> : null}
                  </div>
                </div>
              </div>
              <NextDueLine status={card.status} />
              <section aria-labelledby="pc-vacc" className="space-y-2">
                <h2 id="pc-vacc" className="text-lg">{t("verifiedTitle")}</h2>
                {card.vaccinations.length === 0 ? (
                  <p className="text-ink-2">{tp("status.no_verified_record")}</p>
                ) : (
                  <ul className="divide-y divide-divider rounded-control border border-divider">
                    {card.vaccinations.map((v) => (
                      <li key={v.vaccine} className="space-y-0.5 p-3 text-sm">
                        <p className="font-semibold">{v.vaccine}</p>
                        <p>
                          {tp("givenOn", { date: fmt(v.administered_on) })}
                          {v.next_due_on ? ` · ${tp("nextDue", { date: fmt(v.next_due_on) })}` : ""}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </Card>
            <Notice tone="info" title={t("disclaimerTitle")}>
              <p className="font-semibold">{card.disclaimer}</p>
              <p>{t("verifiedOnly")}</p>
            </Notice>
          </>
        )}
      </div>
    </PublicPage>
  );
}
