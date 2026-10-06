import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button, Card, EmptyState, Notice, StatusChip } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import {
  AnimalThumb,
  ProfileStateChip,
  VaccinationStateChip,
  VaccinationSummaryPanel,
} from "@/components/prevention/evidence";
import { Link } from "@/i18n/navigation";
import { formatDateTime, formatPartialDate, relativeDays } from "@/lib/format";
import { pageContext } from "@/lib/page-context";

import { ProfileActions } from "./profile-actions";

const TABS = ["overview", "vaccinations", "sightings", "tasks", "history"] as const;
type Tab = (typeof TABS)[number];

export default async function AnimalProfilePage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; id: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  const sp = await searchParams;
  const tab: Tab = (TABS as readonly string[]).includes(sp.tab ?? "") ? (sp.tab as Tab) : "overview";
  const ctx = await pageContext();
  const t = await getTranslations("profile");
  const ta = await getTranslations("animal");
  const tc = await getTranslations("common");
  const tn = await getTranslations("nav");
  const tt = await getTranslations("tasks");
  const tz = ctx.tz;

  const { data: animal, response } = await ctx.api.GET("/api/v1/animals/{animal_id}", {
    params: { path: { animal_id: id } },
  });
  if (response.status === 404 || !animal) notFound();

  const usable = !["merged_alias", "archived"].includes(animal.profile_state);
  const title = animal.nickname ? `${animal.nickname} · ${animal.reference_code}` : animal.reference_code;

  return (
    <PageBody wide>
      {sp.created ? (
        <Notice tone="success" title={t("created", { reference: animal.reference_code })} live="polite">
          <p>{t("createdNext")}</p>
        </Notice>
      ) : null}
      {animal.profile_state === "merged_alias" && animal.merged_into_reference ? (
        <Notice tone="info" title={t("mergedBanner", { reference: animal.merged_into_reference })}>
          <p>
            <Link href={`/app/animals?q=${encodeURIComponent(animal.merged_into_reference)}`}>
              {t("openTarget", { reference: animal.merged_into_reference })}
            </Link>
          </p>
        </Notice>
      ) : null}
      {animal.profile_state === "disputed" ? <Notice tone="pending" title={t("disputedBanner")} /> : null}

      <PageHeader title={title} back={{ href: "/app/animals", label: tn("animals") }}>
        <div className="flex flex-wrap items-center gap-4 pt-2">
          <AnimalThumb url={animal.photo?.url} alt={animal.reference_code} size="lg" />
          <div className="space-y-2">
            <div className="flex flex-wrap gap-2">
              <ProfileStateChip state={animal.profile_state} />
              {animal.is_demo ? <StatusChip kind="demo">Demo</StatusChip> : null}
            </div>
            <p className="text-sm text-ink-2">
              {ta("lastSeen")}: {relativeDays(animal.last_observed_at, locale) ?? ta("neverSeen")}
            </p>
            {usable ? (
              <div className="flex flex-wrap gap-2">
                {ctx.can("vaccination.submit") ? (
                  <Button asChild size="sm">
                    <Link href={`/app/animals/${animal.id}/vaccinations/new`}>{t("recordVaccination")}</Link>
                  </Button>
                ) : null}
                {ctx.can("observation.write") ? (
                  <Button asChild variant="secondary" size="sm">
                    <Link href={`/app/capture?animal=${animal.id}`}>{t("addSighting")}</Link>
                  </Button>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      </PageHeader>

      <nav aria-label={t("details")} className="overflow-x-auto border-b border-divider">
        <ul className="flex min-w-max gap-1">
          {TABS.map((k) => (
            <li key={k}>
              <Link
                href={`/app/animals/${animal.id}?tab=${k}`}
                aria-current={tab === k ? "page" : undefined}
                className={`inline-flex min-h-11 items-center border-b-2 px-3 font-display text-sm font-semibold no-underline ${tab === k ? "border-primary text-primary" : "border-transparent text-ink-2 hover:text-ink"}`}
              >
                {t(`tabs.${k}`)}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      {tab === "overview" ? (
        <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
          <div className="space-y-6">
            <VaccinationSummaryPanel summary={animal.vaccination} />
            <Card>
              <h2 className="text-lg">{t("details")}</h2>
              <dl className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-[12rem_1fr]">
                {(
                  [
                    [ta("reference"), animal.reference_code],
                    [ta("species.label"), ta(`species.${animal.species}`)],
                    [ta("sex.label"), ta(`sex.${animal.sex}`)],
                    [ta("sterilisation.label"), ta(`sterilisation.${animal.sterilisation_status}`)],
                    [ta("ageBand.label"), ta(`ageBand.${animal.age_band}`)],
                    [ta("coat"), animal.coat_description ?? tc("notRecorded")],
                    [ta("marks"), animal.identifying_marks ?? tc("notRecorded")],
                    [ta("breed"), animal.breed_note ?? tc("notRecorded")],
                    [ta("ownership.label"), ta(`ownership.${animal.ownership_category}`)],
                    [ta("homeArea"), animal.home_area?.name ?? tc("notRecorded")],
                  ] as const
                ).map(([k, val]) => (
                  <div key={k} className="contents">
                    <dt className="font-semibold">{k}</dt>
                    <dd className="text-ink-2">{val}</dd>
                  </div>
                ))}
              </dl>
            </Card>
          </div>
          <ProfileActions
            animalId={animal.id}
            referenceCode={animal.reference_code}
            profileState={animal.profile_state}
            rowVersion={animal.row_version}
            canWrite={ctx.can("animal.write")}
            canMerge={ctx.can("animal.merge")}
          />
        </div>
      ) : null}

      {tab === "vaccinations" ? <VaccinationsTab animalId={animal.id} locale={locale} /> : null}
      {tab === "sightings" ? <SightingsTab animalId={animal.id} locale={locale} tz={tz} /> : null}
      {tab === "tasks" ? (
        <TasksTab animalId={animal.id} locale={locale} labels={{ empty: t("noTasks"), state: (s) => tt(`states.${s}`) }} />
      ) : null}
      {tab === "history" ? (
        ctx.can("audit.read") ? (
          <HistoryTab animalId={animal.id} locale={locale} tz={tz} />
        ) : (
          <EmptyState title={t("historyRestricted")} />
        )
      ) : null}
    </PageBody>
  );
}

async function VaccinationsTab({ animalId, locale }: { animalId: string; locale: string }) {
  const ctx = await pageContext();
  const t = await getTranslations("profile");
  const tc = await getTranslations("common");
  const tv = await getTranslations("vaccDetail");
  const { data } = await ctx.api.GET("/api/v1/vaccination-events", {
    params: { query: { animal_id: animalId, limit: 50 } },
  });
  if (!data || data.items.length === 0) return <EmptyState title={t("noVaccinations")} />;
  return (
    <ul className="divide-y divide-divider rounded-card border border-divider bg-surface">
      {data.items.map((e) => (
        <li key={e.id}>
          <Link href={`/app/vaccinations/${e.id}`} className="flex flex-wrap items-center gap-3 p-4 text-ink no-underline hover:bg-canvas">
            <div className="min-w-0 flex-1">
              <p className="font-display font-semibold">
                {formatPartialDate(e.administered_on, e.date_precision, locale, tc("notRecorded"))}
              </p>
              <p className="text-sm text-ink-2">
                {[e.product_name ?? e.product_text ?? tc("notRecorded"), e.lot_number ?? e.lot_text].filter(Boolean).join(" · ")}
              </p>
              {e.submitted_by_name ? <p className="text-sm text-ink-2">{t("submittedBy", { name: e.submitted_by_name })}</p> : null}
            </div>
            <div className="flex flex-wrap gap-1.5">
              <VaccinationStateChip state={e.state} />
              {e.has_conflict ? <StatusChip kind="disputed">{tv("conflicts")}</StatusChip> : null}
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}

async function SightingsTab({ animalId, locale, tz }: { animalId: string; locale: string; tz: string }) {
  const ctx = await pageContext();
  const t = await getTranslations("profile");
  const tc = await getTranslations("common");
  const { data } = await ctx.api.GET("/api/v1/animals/{animal_id}/observations", {
    params: { path: { animal_id: animalId } },
  });
  if (!data || data.length === 0) return <EmptyState title={t("noSightings")} />;
  return (
    <ul className="divide-y divide-divider rounded-card border border-divider bg-surface">
      {data.map((o) => (
        <li key={o.id} className="space-y-1 p-4">
          <p className="font-display font-semibold">
            {o.observed_at ? formatDateTime(o.observed_at, locale, tz) : formatPartialDate(o.observed_on, o.time_precision === "exact" ? "day" : o.time_precision, locale, tc("notRecorded"))}
          </p>
          <p className="text-sm text-ink-2">
            {o.area?.name ? `${o.area.name} · ` : ""}
            {o.location ? t(`sightingLocation.${o.location.precision}`, { lat: o.location.lat, lon: o.location.lon }) : t("sightingLocation.none")}
          </p>
          {o.observer_name ? <p className="text-sm text-ink-2">{t("observer", { name: o.observer_name })}</p> : null}
          {o.notes ? <p className="text-sm">{o.notes}</p> : null}
          {o.media_ids.length ? <p className="text-sm text-ink-2">{t("photos", { count: o.media_ids.length })}</p> : null}
        </li>
      ))}
    </ul>
  );
}

async function TasksTab({
  animalId,
  locale,
  labels,
}: {
  animalId: string;
  locale: string;
  labels: { empty: string; state: (s: string) => string };
}) {
  const ctx = await pageContext();
  const tt = await getTranslations("tasks");
  const tc = await getTranslations("common");
  const { data } = await ctx.api.GET("/api/v1/tasks", { params: { query: { mine: false, animal_id: animalId } } });
  if (!data || data.items.length === 0) return <EmptyState title={labels.empty} />;
  return (
    <ul className="divide-y divide-divider rounded-card border border-divider bg-surface">
      {data.items.map((task) => (
        <li key={task.id} className="flex flex-wrap items-center justify-between gap-2 p-4">
          <div>
            <p className="font-display font-semibold">{task.title}</p>
            <p className="text-sm text-ink-2">
              {tt(`types.${task.task_type}`)}
              {task.due_on ? ` · ${tt("dueOn", { date: formatPartialDate(task.due_on, "day", locale, tc("notRecorded")) })}` : ""}
            </p>
          </div>
          <StatusChip kind={task.state === "blocked" ? "disputed" : task.state === "completed" ? "verified" : "neutral"}>
            {labels.state(task.state)}
          </StatusChip>
        </li>
      ))}
    </ul>
  );
}

async function HistoryTab({ animalId, locale, tz }: { animalId: string; locale: string; tz: string }) {
  const ctx = await pageContext();
  const t = await getTranslations("profile");
  const { data } = await ctx.api.GET("/api/v1/audit", { params: { query: { target_id: animalId } } });
  if (!data || data.length === 0) return <EmptyState title={t("noHistory")} />;
  return (
    <ol className="space-y-2">
      {data.map((e) => (
        <li key={e.id} className="rounded-control border border-divider bg-surface p-3 text-sm">
          <p className="font-semibold">
            <span className="font-mono">{e.action}</span> · {e.actor_name ?? e.actor_kind}
          </p>
          <p className="text-ink-2">{formatDateTime(e.occurred_at, locale, tz)}</p>
          {e.reason ? <p>{e.reason}</p> : null}
        </li>
      ))}
    </ol>
  );
}
