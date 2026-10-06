"use client";

import type { Schemas } from "@pawguard/api-client";
import { AlertTriangle, CalendarClock, CalendarRange, ClipboardCheck } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { StatusChip, cn } from "@pawguard/ui";

import { Link } from "@/i18n/navigation";
import { formatPartialDate } from "@/lib/format";

import { NextDueLine, PetStatusChip } from "./status";

type Dash = Schemas["ClinicDashboardOut"];
type Row = Schemas["ClinicPetRowOut"];
type Filter = "all" | "awaiting" | "overdue" | "week" | "soon";

/** Count tiles that filter the lists below; the verification queue comes first (the vet's main job). */
export function ClinicBoard({ d, canReview }: { d: Dash; canReview: boolean }) {
  const t = useTranslations("clinic");
  const tc = useTranslations("common");
  const locale = useLocale();
  const [filter, setFilter] = useState<Filter>("all");
  const tiles = [
    { key: "awaiting", label: t("awaiting"), count: d.awaiting_verification.length, Icon: ClipboardCheck, tone: "bg-sky" },
    { key: "overdue", label: t("overdue"), count: d.overdue.length, Icon: AlertTriangle, tone: "bg-urgent-soft" },
    { key: "week", label: t("dueThisWeek"), count: d.due_this_week.length, Icon: CalendarClock, tone: "bg-sand" },
    { key: "soon", label: t("dueSoon"), count: d.due_soon.length, Icon: CalendarRange, tone: "bg-sage" },
  ] as const;
  const show = (f: Filter) => filter === "all" || filter === f;

  const list = (id: string, title: string, rows: Row[], empty: string) => (
    <section aria-labelledby={id} className="space-y-2">
      <h2 id={id} className="text-lg">
        {title} <span className="text-ink-2">({rows.length})</span>
      </h2>
      {rows.length === 0 ? (
        <p className="text-ink-2">{empty}</p>
      ) : (
        <ul className="divide-y divide-divider rounded-card border border-divider bg-surface">
          {rows.map((r) => (
            <li key={r.pet_id} className="flex flex-wrap items-start justify-between gap-2 p-3">
              <div className="min-w-0 space-y-1">
                <Link href={`/app/animals/${r.pet_id}`} className="font-display font-semibold">
                  {r.pet_name}
                </Link>
                <span className="ml-2 font-mono text-xs text-ink-2">{r.reference_code}</span>
                <NextDueLine status={r.status} />
                {!r.owner_linked ? <p className="text-sm text-ink-2">{t("noOwner")}</p> : null}
              </div>
              <PetStatusChip status={r.status} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" data-tour="clinic-tiles" role="group" aria-label={t("filterLabel")}>
        {tiles.map(({ key, label, count, Icon, tone }) => {
          const pressed = filter === key;
          return (
            <button
              key={key}
              type="button"
              aria-pressed={pressed}
              onClick={() => setFilter(pressed ? "all" : key)}
              className={cn(
                "flex min-h-24 flex-col items-start justify-between rounded-card border-2 p-4 text-left motion-safe:transition-colors motion-safe:duration-150",
                tone,
                pressed ? "border-primary" : "border-transparent hover:border-control",
              )}
            >
              <span className="flex items-center gap-1.5 text-sm font-semibold">
                <Icon aria-hidden className={cn("size-4", key === "overdue" ? "text-urgent" : "text-primary")} />
                {label}
              </span>
              <span className="font-display text-3xl font-bold">{count}</span>
            </button>
          );
        })}
      </div>
      {filter !== "all" ? (
        <p role="status" className="flex flex-wrap items-center gap-2 text-sm">
          {t("filteredBy", { name: tiles.find((x) => x.key === filter)?.label ?? "" })}
          <button type="button" onClick={() => setFilter("all")} className="min-h-11 font-semibold text-primary underline underline-offset-4">
            {t("showAll")}
          </button>
        </p>
      ) : null}

      {show("awaiting") ? (
        <section aria-labelledby="awaiting" className="space-y-2" data-tour="clinic-queue">
          <h2 id="awaiting" className="text-lg">
            {t("awaiting")} <span className="text-ink-2">({d.awaiting_verification.length})</span>
          </h2>
          {d.awaiting_verification.length === 0 ? (
            <p className="text-ink-2">{t("noneAwaiting")}</p>
          ) : (
            <ul className="divide-y divide-divider rounded-card border-2 border-sky bg-surface">
              {d.awaiting_verification.map((a) => (
                <li key={a.event_id} className="flex flex-wrap items-center justify-between gap-3 p-3">
                  <div className="min-w-0">
                    <p className="font-display font-semibold">{a.pet_name}</p>
                    <p className="text-sm text-ink-2">
                      {a.vaccine} · {formatPartialDate(a.administered_on, "day", locale, tc("notRecorded"))}
                    </p>
                    {a.entered_by_owner ? <StatusChip kind="submitted">{t("enteredByOwner")}</StatusChip> : null}
                  </div>
                  <Link
                    href={canReview ? `/app/review?id=${a.event_id}` : `/app/vaccinations/${a.event_id}`}
                    className="inline-flex min-h-11 items-center rounded-control bg-primary px-4 font-display text-sm font-semibold text-white no-underline hover:bg-primary-hover"
                  >
                    {canReview ? t("openReview") : tc("view")}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}
      <div className="grid gap-6 lg:grid-cols-2">
        {show("overdue") ? list("overdue", t("overdue"), d.overdue, t("noneOverdue")) : null}
        {show("week") ? list("due-week", t("dueThisWeek"), d.due_this_week, t("noneDueThisWeek")) : null}
        {show("soon") ? list("due-soon", t("dueSoon"), d.due_soon, t("noneDueSoon")) : null}
      </div>
    </div>
  );
}
