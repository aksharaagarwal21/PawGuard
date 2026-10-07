import { AlertTriangle, Mail, Phone } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Notice, StatusChip } from "@pawguard/ui";

import { DisputeForm, OwnerCheckin } from "@/components/bite/owner-actions";
import { ObservationTimeline } from "@/components/bite/timeline";
import { PageBody, PageHeader } from "@/components/page-header";
import { formatPartialDate } from "@/lib/format";
import { pageContext } from "@/lib/page-context";

/** Owner: bite reports about their pets — the daily one-tap update, the timeline, contact the vet, dispute. */
export default async function OwnerBitesPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  const t = await getTranslations("bite.owner");
  const ts = await getTranslations("bite.share");
  const { data } = await ctx.api.GET("/api/v1/my/bites");
  const cases = data ?? [];
  const fmt = (d: string) => formatPartialDate(d, "day", locale, "—");
  return (
    <PageBody>
      <PageHeader title={t("listTitle")} intro={t("listIntro")} />
      {cases.length === 0 ? <p className="text-ink-2">{t("none")}</p> : null}
      {cases.map((c) => {
        const obs = c.observation;
        const today = obs.timeline.find((d) => d.day === obs.current_day);
        const changed = obs.urgent;
        return (
          <article key={c.period_id} aria-labelledby={`case-${c.period_id}`} className="space-y-4 rounded-card border border-divider bg-canvas p-4" data-testid="bite-case">
            <h2 id={`case-${c.period_id}`} className="text-xl">
              {t("caseTitle", { pet: c.pet_name, date: fmt(obs.bite_date) })}
            </h2>
            {c.disputed ? <StatusChip kind="needs_correction">{t("disputed")}</StatusChip> : null}
            {!obs.ended ? <p className="font-semibold">{t("intro", { pet: c.pet_name, days: obs.length_days })}</p> : null}
            <section className={changed ? "space-y-2 rounded-card border-l-8 border-urgent bg-urgent-soft p-4" : "space-y-2"}>
              <p className="flex items-center gap-2 font-display text-lg font-semibold">
                {changed ? <AlertTriangle aria-hidden className="size-5 text-urgent" /> : null}
                {changed ? t("contactVetNow") : t("contactVet")}
              </p>
              <p className="flex flex-wrap gap-4">
                <span>{c.clinic_name}</span>
                {c.clinic_email ? (
                  <a href={`mailto:${c.clinic_email}`} className="inline-flex min-h-11 items-center gap-1.5">
                    <Mail aria-hidden className="size-4" /> {t("email", { email: c.clinic_email })}
                  </a>
                ) : null}
                {c.clinic_phone ? (
                  <a href={`tel:${c.clinic_phone}`} className="inline-flex min-h-11 items-center gap-1.5">
                    <Phone aria-hidden className="size-4" /> {t("call", { phone: c.clinic_phone })}
                  </a>
                ) : null}
              </p>
            </section>
            {!obs.ended && obs.current_day >= 1 ? (
              <OwnerCheckin periodId={c.period_id} day={obs.current_day} days={obs.length_days} current={today?.owner_state ?? null} />
            ) : null}
            <ObservationTimeline obs={obs} pet={c.pet_name} />
            <section aria-label={t("reportsTitle")} className="space-y-1 text-sm">
              <h3 className="font-display font-semibold">{t("reportsTitle")}</h3>
              <ul className="space-y-1">
                {c.reports.map((r) => (
                  <li key={r.reference}>
                    {r.reference}
                    {r.bite_time ? ` · ${r.bite_time}` : ""} · {r.bitten === "animal" ? ts("bittenAnimal") : ts("bittenPerson")}
                    {r.area ? ` · ${r.area}` : ""}
                    {r.possible_duplicate ? <span className="block text-ink-2">{t("possibleDuplicate")}</span> : null}
                    {r.contact ? <span className="block">{t("sharedContact", { contact: r.contact })}</span> : null}
                  </li>
                ))}
              </ul>
            </section>
            {!c.disputed ? <DisputeForm periodId={c.period_id} /> : <Notice tone="info">{t("disputed")}</Notice>}
          </article>
        );
      })}
    </PageBody>
  );
}
