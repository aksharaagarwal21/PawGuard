import { ChevronRight, Plus, Search } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button, EmptyState, Notice } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { AnimalThumb, ProfileStateChip, VaccinationSummaryChip } from "@/components/prevention/evidence";
import { Link } from "@/i18n/navigation";
import { relativeDays } from "@/lib/format";
import { pageContext } from "@/lib/page-context";

type SP = Record<string, string | undefined>;
const STATES = ["provisional", "reviewed", "active", "disputed", "archived"] as const;

export default async function RegistryPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<SP>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const sp = await searchParams;
  const ctx = await pageContext();
  const t = await getTranslations("registry");
  const ta = await getTranslations("animal");
  const tc = await getTranslations("common");
  const tn = await getTranslations("nav");
  const tps = await getTranslations("profileState");

  const query = {
    q: sp.q || undefined,
    area_id: sp.area || undefined,
    profile_state: sp.state && (STATES as readonly string[]).includes(sp.state) ? [sp.state as (typeof STATES)[number]] : undefined,
    vaccination_status: (["verified_record", "submitted_only", "no_verified_record"] as const).find((v) => v === sp.vacc),
    seen_within_days: sp.seen ? Number(sp.seen) : undefined,
    has_open_task: sp.task === "1" ? true : undefined,
    cursor: sp.cursor || undefined,
    limit: 25,
  };
  const [{ data, error }, { data: areas }] = await Promise.all([
    ctx.api.GET("/api/v1/animals", { params: { query } }),
    ctx.api.GET("/api/v1/areas"),
  ]);
  const filtersActive = Boolean(sp.q || sp.area || sp.state || sp.vacc || sp.seen || sp.task);
  const keep = (extra: Record<string, string | undefined>) => {
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries({ ...sp, ...extra })) if (v) u.set(k, v);
    const s = u.toString();
    return s ? `/app/animals?${s}` : "/app/animals";
  };

  return (
    <PageBody wide>
      <PageHeader
        title={t("title")}
        intro={t("intro")}
        actions={
          ctx.can("animal.write") ? (
            <Button asChild>
              <Link href="/app/animals/new">
                <Plus aria-hidden className="size-4" />
                {tn("registerAnimal")}
              </Link>
            </Button>
          ) : null
        }
      />

      <form method="get" className="space-y-3 rounded-card border border-divider bg-surface p-4" role="search">
        <label htmlFor="q" className="font-display text-sm font-semibold">
          {t("searchLabel")}
        </label>
        <div className="flex gap-2">
          <input
            id="q"
            name="q"
            defaultValue={sp.q ?? ""}
            placeholder={t("searchPlaceholder")}
            maxLength={80}
            className="min-h-11 w-full rounded-control border border-control bg-surface px-3"
          />
          <Button type="submit">
            <Search aria-hidden className="size-4" />
            <span className="sr-only sm:not-sr-only">{tc("search")}</span>
          </Button>
        </div>
        <details open={filtersActive} className="group">
          <summary className="inline-flex min-h-11 cursor-pointer items-center font-display text-sm font-semibold text-primary">
            {tc("filters")}
          </summary>
          <div className="grid gap-3 pt-2 sm:grid-cols-2 lg:grid-cols-5">
            <FilterSelect name="area" label={t("area")} value={sp.area} options={[["", t("anyArea")], ...(areas ?? []).map((a) => [a.id, a.name] as [string, string])]} />
            <FilterSelect name="state" label={t("reviewState")} value={sp.state} options={[["", t("anyState")], ...STATES.map((s) => [s, tps(s)] as [string, string])]} />
            <FilterSelect
              name="vacc"
              label={t("vaccination")}
              value={sp.vacc}
              options={[
                ["", t("anyVaccination")],
                ["verified_record", t("vaccinationOptions.verified_record")],
                ["submitted_only", t("vaccinationOptions.submitted_only")],
                ["no_verified_record", t("vaccinationOptions.no_verified_record")],
              ]}
            />
            <FilterSelect name="seen" label={t("seen")} value={sp.seen} options={[["", t("anyTime")], ["30", t("seenWithin.30")], ["90", t("seenWithin.90")], ["180", t("seenWithin.180")]]} />
            <FilterSelect name="task" label={t("tasksFilter")} value={sp.task} options={[["", tc("all")], ["1", t("withTasks")]]} />
          </div>
          <div className="flex flex-wrap gap-3 pt-3">
            <Button type="submit" variant="secondary" size="sm">
              {tc("search")}
            </Button>
            {filtersActive ? (
              <Link href="/app/animals" className="inline-flex min-h-11 items-center text-sm font-semibold">
                {tc("clearFilters")}
              </Link>
            ) : null}
          </div>
        </details>
      </form>

      {error ? (
        <Notice tone="urgent" title={tc("tryAgainLater")} live="alert">
          {error.error?.message}
        </Notice>
      ) : data && data.items.length === 0 ? (
        <EmptyState
          title={t("noResultsTitle")}
          action={
            ctx.can("animal.write") ? (
              <Button asChild variant="secondary">
                <Link href="/app/animals/new">{tn("registerAnimal")}</Link>
              </Button>
            ) : undefined
          }
        >
          {t("noResultsBody")}
        </EmptyState>
      ) : data ? (
        <section aria-labelledby="results">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="results" className="text-base">
              {t("results", { count: data.total_matching ?? data.items.length })}
            </h2>
            <p className="text-sm text-ink-2">{t("registryNote")}</p>
          </div>
          <ul className="mt-3 divide-y divide-divider overflow-hidden rounded-card border border-divider bg-surface">
            {data.items.map((a) => (
              <li key={a.id}>
                <Link
                  href={`/app/animals/${a.id}`}
                  className="flex items-center gap-3 p-3 text-ink no-underline hover:bg-canvas sm:gap-4 sm:p-4"
                >
                  <AnimalThumb url={a.photo?.url} alt={t("photoAlt", { reference: a.reference_code })} />
                  <div className="min-w-0 flex-1 space-y-1">
                    <p className="flex flex-wrap items-baseline gap-x-2">
                      <span className="font-mono text-sm font-semibold">{a.reference_code}</span>
                      <span className="font-display font-semibold">{a.nickname ?? <span className="font-normal text-ink-2">{ta("noNickname")}</span>}</span>
                    </p>
                    <p className="truncate text-sm text-ink-2">
                      {[a.coat_description, a.home_area?.name].filter(Boolean).join(" · ") || tc("notRecorded")}
                    </p>
                    <p className="text-sm text-ink-2">
                      {ta("lastSeen")}: {relativeDays(a.last_observed_at, locale) ?? ta("neverSeen")}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      <ProfileStateChip state={a.profile_state} />
                      <VaccinationSummaryChip summary={a.vaccination} />
                    </div>
                  </div>
                  <ChevronRight aria-hidden className="size-5 shrink-0 text-ink-2" />
                </Link>
              </li>
            ))}
          </ul>
          <nav aria-label={tc("pagination")} className="mt-4 flex justify-between gap-3">
            {sp.cursor ? (
              <Link href={keep({ cursor: undefined })} className="inline-flex min-h-11 items-center font-semibold">
                {tc("firstPage")}
              </Link>
            ) : (
              <span />
            )}
            {data.next_cursor ? (
              <Link href={keep({ cursor: data.next_cursor })} className="inline-flex min-h-11 items-center font-semibold">
                {tc("nextPage")}
              </Link>
            ) : null}
          </nav>
        </section>
      ) : null}
    </PageBody>
  );
}

function FilterSelect({
  name,
  label,
  value,
  options,
}: {
  name: string;
  label: string;
  value?: string;
  options: [string, string][];
}) {
  return (
    <label className="block text-sm">
      <span className="font-display font-semibold">{label}</span>
      <select
        name={name}
        defaultValue={value ?? ""}
        className="mt-1 min-h-11 w-full rounded-control border border-control bg-surface px-2"
      >
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
}
