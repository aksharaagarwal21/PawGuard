import { AlertTriangle, HelpCircle, Scale } from "lucide-react";
import { getLocale, getTranslations } from "next-intl/server";

import { StatusChip } from "@pawguard/ui";

import { VetExamForm } from "@/components/bite/owner-actions";
import { formatPartialDate } from "@/lib/format";
import { pageContext } from "@/lib/page-context";

/** Clinic dashboard: bite reports about this clinic's pets — changes reported, missed days and disputes first.
 *  No reporter contact details. Vets can record an examination ("Vet-recorded"). */
export async function ClinicBites({ canReview }: { canReview: boolean }) {
  const ctx = await pageContext();
  const t = await getTranslations("bite.clinic");
  const ts = await getTranslations("bite.share");
  const locale = await getLocale();
  const { data } = await ctx.api.GET("/api/v1/clinic/bites");
  if (!data) return null;
  const fmt = (d: string) => formatPartialDate(d, "day", locale, "—");
  return (
    <section aria-labelledby="bites-h" className="space-y-3 rounded-card border border-divider bg-surface p-4" data-testid="clinic-bites">
      <h2 id="bites-h" className="text-lg">
        {t("title")}
      </h2>
      <p className="text-sm text-ink-2">{t("intro")}</p>
      {data.length === 0 ? <p className="text-sm text-ink-2">{t("none")}</p> : null}
      <ul className="divide-y divide-divider">
        {data.map((c) => {
          const o = c.observation;
          return (
            <li key={c.period_id} className="space-y-1.5 py-3" data-urgent={o.urgent ? "true" : "false"}>
              <p className="font-semibold">
                {c.pet_name} · {ts("biteOn", { date: fmt(o.bite_date) })}
              </p>
              <p className="text-sm">
                {o.ended ? ts(`ended.${o.status as "completed" | "completed_with_gaps" | "change_reported"}`) : t("dayOf", { day: Math.max(o.current_day, 0), days: o.length_days })}
              </p>
              <div className="flex flex-wrap gap-2 text-sm">
                {o.urgent ? (
                  <span className="inline-flex items-center gap-1 font-semibold text-urgent">
                    <AlertTriangle aria-hidden className="size-4" /> {t("urgent")}
                  </span>
                ) : null}
                {o.missed_days ? (
                  <span className="inline-flex items-center gap-1">
                    <HelpCircle aria-hidden className="size-4" /> {t("missed", { count: o.missed_days })}
                  </span>
                ) : null}
                {c.disputed ? (
                  <span className="inline-flex items-center gap-1">
                    <Scale aria-hidden className="size-4" /> {t("disputed")}
                  </span>
                ) : null}
                {c.possible_duplicate ? <StatusChip kind="neutral">{t("duplicate")}</StatusChip> : null}
              </div>
              {canReview && !o.ended && o.current_day >= 1 ? <VetExamForm periodId={c.period_id} /> : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
