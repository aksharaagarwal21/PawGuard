import type { Schemas } from "@pawguard/api-client";
import { AlertTriangle, CheckCircle2, Clock, HelpCircle } from "lucide-react";
import { getLocale, getTranslations } from "next-intl/server";

import { cn } from "@pawguard/ui";

import { formatPartialDate } from "@/lib/format";

type Observation = Schemas["BiteObservationOut"];

const ICON = { normal: CheckCircle2, change: AlertTriangle, no_update: HelpCircle, awaiting: Clock } as const;

/** Day-by-day observation. A day without an update says "No update" — it is never shown as normal. */
export async function ObservationTimeline({ obs, pet }: { obs: Observation; pet: string }) {
  const t = await getTranslations("bite.share");
  const locale = await getLocale();
  const fmt = (d: string) => formatPartialDate(d, "day", locale, "—");
  return (
    <section aria-labelledby="obs-h" className="space-y-3" data-testid="observation">
      <h2 id="obs-h" className="text-xl">
        {t("observationTitle", { pet })}
      </h2>
      <p className="text-sm text-ink-2">{t("policy", { days: obs.length_days })}</p>
      {obs.ended ? (
        <p className={cn("rounded-control p-3 font-semibold", obs.status === "completed" ? "bg-sage" : "bg-sand")}>
          {t(`ended.${obs.status as "completed" | "completed_with_gaps" | "change_reported"}`)} {t("endedNote")}
        </p>
      ) : null}
      {obs.current_day < 1 ? <p>{t("notStarted")}</p> : null}
      <ol className="divide-y divide-divider rounded-control border border-divider bg-surface">
        {obs.timeline.map((d) => {
          const Icon = ICON[d.status];
          return (
            <li key={d.day} className="flex flex-wrap items-start gap-x-3 gap-y-1 p-3" data-day-status={d.status}>
              <span className="w-24 shrink-0 font-semibold">
                {t("day", { day: d.day })}
                <span className="block text-xs font-normal text-ink-2">{fmt(d.date)}</span>
              </span>
              <span className={cn("flex min-w-0 flex-1 items-start gap-2", d.status === "change" && "font-semibold text-urgent")}>
                <Icon aria-hidden className="mt-0.5 size-4 shrink-0" />
                <span>
                  {t(`dayStatus.${d.status}`)}
                  {d.owner_state ? (
                    <span className="block text-sm text-ink">
                      {t(`state.${d.owner_state}`)} · <span className="text-ink-2">{t("ownerReported")}</span>
                    </span>
                  ) : null}
                  {d.vet_state ? (
                    <span className="block text-sm text-ink">
                      {t(`state.${d.vet_state}`)} · <span className="font-semibold">{t("vetRecorded")}</span>
                    </span>
                  ) : null}
                </span>
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
