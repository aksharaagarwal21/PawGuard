import type { Schemas } from "@pawguard/api-client";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Card, Notice, StatusChip } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { ClinicRecordForm } from "@/components/pets/clinic-record-form";
import { DemoClockControl } from "@/components/pets/demo-clock";
import { NextDueLine, PetStatusChip } from "@/components/pets/status";
import { Link } from "@/i18n/navigation";
import { formatPartialDate } from "@/lib/format";
import { pageContext } from "@/lib/page-context";

type Row = Schemas["ClinicPetRowOut"];

/** Clinic staff: this clinic's registered pets that are due, overdue or waiting for a vet's verification. */
export default async function ClinicPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  const t = await getTranslations("clinic");
  const tc = await getTranslations("common");
  const { data: d, error } = await ctx.api.GET("/api/v1/clinic/dashboard");
  if (!d) return <PageBody><Notice tone="urgent">{error?.error?.message ?? tc("tryAgainLater")}</Notice></PageBody>;
  const canReview = ctx.can("vaccination.review");
  const realToday = new Date().toLocaleDateString("en-CA", { timeZone: ctx.tz });

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
    <PageBody wide>
      <PageHeader title={t("title")} intro={t("intro")} />
      <Card className="space-y-1">
        <p className="font-display text-xl font-semibold">{t("upToDate", { up: d.up_to_date, total: d.pets_total })}</p>
        <p className="text-sm font-semibold text-ink-2">{t("coverageNote")}</p>
        <p className="text-sm text-ink-2">
          {t("noVerified", { count: d.no_verified_record })} · {t("unverifiedOnly", { count: d.unverified_only })}
        </p>
      </Card>
      {d.demo_clock_available ? <DemoClockControl offsetDays={d.demo_offset_days} today={d.today} /> : null}
      <div className="grid gap-6 lg:grid-cols-2">
        {list("due-week", t("dueThisWeek"), d.due_this_week, t("noneDueThisWeek"))}
        {list("overdue", t("overdue"), d.overdue, t("noneOverdue"))}
        {list("due-soon", t("dueSoon"), d.due_soon, t("noneDueSoon"))}
        <section aria-labelledby="awaiting" className="space-y-2">
          <h2 id="awaiting" className="text-lg">
            {t("awaiting")} <span className="text-ink-2">({d.awaiting_verification.length})</span>
          </h2>
          {d.awaiting_verification.length === 0 ? (
            <p className="text-ink-2">{t("noneAwaiting")}</p>
          ) : (
            <ul className="divide-y divide-divider rounded-card border border-divider bg-surface">
              {d.awaiting_verification.map((a) => (
                <li key={a.event_id} className="flex flex-wrap items-center justify-between gap-2 p-3">
                  <div className="min-w-0">
                    <p className="font-display font-semibold">{a.pet_name}</p>
                    <p className="text-sm text-ink-2">
                      {a.vaccine} · {formatPartialDate(a.administered_on, "day", locale, tc("notRecorded"))}
                    </p>
                    {a.entered_by_owner ? <StatusChip kind="submitted">{t("enteredByOwner")}</StatusChip> : null}
                  </div>
                  <Link href={canReview ? `/app/review?id=${a.event_id}` : `/app/vaccinations/${a.event_id}`} className="font-semibold">
                    {canReview ? t("openReview") : tc("view")}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
      {canReview && d.pets.length > 0 && d.products.length > 0 ? (
        <section aria-labelledby="record" className="space-y-3 rounded-card border border-divider bg-surface p-4">
          <h2 id="record" className="text-lg">{t("record.title")}</h2>
          <p className="text-sm text-ink-2">{t("record.intro")}</p>
          <ClinicRecordForm pets={d.pets} products={d.products} today={realToday} />
        </section>
      ) : null}
    </PageBody>
  );
}
