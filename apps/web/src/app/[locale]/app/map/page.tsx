import type { FeatureCollection } from "geojson";
import { Download } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Card, Notice } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { formatDateTime } from "@/lib/format";
import { pageContext } from "@/lib/page-context";
import { serverEnv } from "@/lib/server-env";

import { STATUS_COLOURS } from "./area-map";
import { LazyAreaMap } from "./map-loader";

export default async function MapPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  const t = await getTranslations("map");
  const te = await getTranslations("errors");
  if (!ctx.can("animal.read")) {
    return (
      <PageBody>
        <Notice tone="urgent" title={te("forbiddenTitle")}>{te("forbiddenBody")}</Notice>
      </PageBody>
    );
  }
  const env = serverEnv();
  const [{ data: layers }, { data: summary }] = await Promise.all([
    ctx.api.GET("/api/v1/map/layers"),
    ctx.api.GET("/api/v1/programme/summary"),
  ]);
  const l = layers as
    | { precision: string; truncated: boolean; areas: FeatureCollection; sightings: FeatureCollection; tasks: FeatureCollection }
    | undefined;
  return (
    <PageBody wide>
      <PageHeader
        title={t("title")}
        intro={t("intro")}
        actions={
          ctx.can("report.aggregate") ? (
            <a
              href="/api/v1/exports/animals.csv"
              className="inline-flex min-h-11 items-center gap-2 rounded-control border border-control bg-surface px-4 font-display text-sm font-semibold text-ink no-underline hover:bg-sage"
            >
              <Download aria-hidden className="size-4" />
              {t("export")}
            </a>
          ) : null
        }
      />
      {l ? (
        <>
          <p className="text-sm text-ink-2">
            {l.precision === "exact" ? t("precisionExact") : t("precisionApprox")} {env.PAWGUARD_MAP_TILE_URL ? "" : t("noBasemap")}{" "}
            {l.truncated ? t("truncated") : ""}
          </p>
          <LazyAreaMap
            areas={l.areas}
            sightings={l.sightings}
            tasks={l.tasks}
            tileUrl={env.PAWGUARD_MAP_TILE_URL || undefined}
            attribution={env.PAWGUARD_MAP_TILE_ATTRIBUTION}
            label={t("mapLabel")}
            locale={locale}
            labels={{
              status_up_to_date: t("status.up_to_date"),
              status_verified: t("status.verified"),
              status_due_soon: t("status.due_soon"),
              status_overdue: t("status.overdue"),
              status_no_verified_record: t("status.no_verified_record"),
              lastVerified: t("popup.lastVerified"),
              nextDue: t("popup.nextDue"),
              seen: t("popup.seen"),
              openRecord: t("popup.openRecord"),
              openTasks: t("popup.openTasks"),
              species_dog: t("popup.dog"),
              species_cat: t("popup.cat"),
              task_unassigned: t("popup.taskUnassigned"),
              task_assigned: t("popup.taskAssigned"),
              task_in_progress: t("popup.taskInProgress"),
              task_blocked: t("popup.taskBlocked"),
            }}
          />
          <div className="flex flex-wrap gap-4 text-sm" aria-label={t("legend")}>
            {(["up_to_date", "due_soon", "overdue", "no_verified_record"] as const).map((s) => (
              <span key={s} className="inline-flex items-center gap-2">
                <span aria-hidden className="inline-block size-3 rounded-full ring-2 ring-white" style={{ backgroundColor: STATUS_COLOURS[s] }} />
                {t("legendSighting", { status: t(`status.${s}`) })}
              </span>
            ))}
            <span className="inline-flex items-center gap-2"><span aria-hidden className="inline-block size-4 rounded-full border-[3px] border-urgent" />{t("legendTasks")}</span>
            <span className="inline-flex items-center gap-2"><span aria-hidden className="inline-block h-3 w-5 border-2 border-primary bg-primary/10" />{t("legendAreas")}</span>
          </div>
          <p className="text-sm text-ink-2">{t("showList")}</p>
        </>
      ) : null}
      {summary ? (
        <Card>
          <h2 className="text-lg">{t("listTitle")}</h2>
          <p className="mt-1 text-sm text-ink-2">{t("registryNote")}</p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead>
                <tr className="border-b border-divider">
                  {(["area", "registered", "verified", "pendingOnly", "sightings", "tasks", "awaiting"] as const).map((c) => (
                    <th key={c} scope="col" className="py-2 pr-3 font-display font-semibold">
                      {t(`columns.${c}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...summary.areas, summary.totals].map((a, i) => (
                  <tr key={a.area_id ?? `total-${i}`} className={`border-b border-divider ${a.area_id === null && i === summary.areas.length ? "font-semibold" : ""}`}>
                    <th scope="row" className="py-2 pr-3 font-normal">{i === summary.areas.length ? t("totals") : a.area_name}</th>
                    <td className="py-2 pr-3">{a.registered_animals}</td>
                    <td className="py-2 pr-3">{a.animals_with_verified_record}</td>
                    <td className="py-2 pr-3">{a.animals_with_pending_evidence_only}</td>
                    <td className="py-2 pr-3">{a.sightings_last_30_days}</td>
                    <td className="py-2 pr-3">{a.open_tasks}</td>
                    <td className="py-2 pr-3">{a.submitted_awaiting_review}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-ink-2">
            {t("generated", { time: formatDateTime(summary.generated_at, locale, ctx.tz), mode: summary.data_mode === "demo" ? t("modeDemo") : t("modeLive") })}
          </p>
        </Card>
      ) : null}
    </PageBody>
  );
}
