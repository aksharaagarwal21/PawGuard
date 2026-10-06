import { FileText } from "lucide-react";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button, Card, Notice, StatusChip } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { VaccinationStateChip } from "@/components/prevention/evidence";
import { Link } from "@/i18n/navigation";
import { formatDateTime, formatPartialDate } from "@/lib/format";
import { pageContext } from "@/lib/page-context";

export default async function VaccinationDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; id: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  const sp = await searchParams;
  const ctx = await pageContext();
  const t = await getTranslations("vaccDetail");
  const tf = await getTranslations("vaccForm");
  const te = await getTranslations("evidence");
  const tc = await getTranslations("common");
  const { data: e } = await ctx.api.GET("/api/v1/vaccination-events/{event_id}", { params: { path: { event_id: id } } });
  if (!e) notFound();
  const nr = tc("notRecorded");
  const mine = e.submitted_by === ctx.me.user_id;
  const lastReview = e.reviews.at(-1);

  return (
    <PageBody>
      {sp.submitted ? <Notice tone="success" title={tf("submitted")} live="polite">{tf("whatNext")}</Notice> : null}
      <PageHeader title={t("title")} back={{ href: `/app/animals/${e.animal_id}?tab=vaccinations`, label: e.animal_reference }}>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <VaccinationStateChip state={e.state} />
          {e.has_conflict ? <StatusChip kind="disputed">{t("conflicts")}</StatusChip> : null}
          {e.is_demo ? <StatusChip kind="demo">Demo</StatusChip> : null}
        </div>
        <p className="text-ink-2">{te(`stateExplain.${e.state}`)}</p>
      </PageHeader>

      {e.state === "needs_correction" && lastReview?.reason ? (
        <Notice tone="pending" title={te("state.needs_correction")}>
          <p>{tf("reviewerReason", { reason: lastReview.reason })}</p>
          {mine || ctx.can("task.manage") ? (
            <p className="pt-2">
              <Button asChild size="sm">
                <Link href={`/app/vaccinations/${e.id}/amend`}>{t("correct")}</Link>
              </Button>
            </p>
          ) : null}
        </Notice>
      ) : null}
      {e.state === "rejected" && lastReview?.reason ? (
        <Notice tone="urgent" title={te("state.rejected")}>
          <p>{lastReview.reason}</p>
        </Notice>
      ) : null}
      {e.conflicts.length ? (
        <Notice tone="pending" title={t("conflicts")}>
          <ul className="list-disc pl-5">
            {e.conflicts.map((c) => (
              <li key={c}>{t.has(`conflictRules.${c}`) ? t(`conflictRules.${c}`) : c}</li>
            ))}
          </ul>
        </Notice>
      ) : null}
      {e.superseded_by_event_id ? (
        <Notice tone="info" title={t("supersededBy")}>
          <Link href={`/app/vaccinations/${e.superseded_by_event_id}`}>{tc("view")}</Link>
        </Notice>
      ) : null}
      {e.supersedes_event_id ? (
        <p className="text-sm">
          {t("supersedes")}: <Link href={`/app/vaccinations/${e.supersedes_event_id}`}>{tc("view")}</Link>
        </p>
      ) : null}

      <Card>
        <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-[12rem_1fr]">
          {(
            [
              [t("animal"), <Link key="a" href={`/app/animals/${e.animal_id}`}>{e.animal_reference}</Link>],
              [t("date"), formatPartialDate(e.administered_on, e.date_precision, locale, nr)],
              [t("product"), e.product_name ?? e.product_text ?? nr],
              [t("lot"), e.lot_number ?? e.lot_text ?? nr],
              [t("administeredBy"), e.administered_by_name ?? nr],
              [t("registration"), e.administered_by_registration ?? nr],
              [t("area"), e.area?.name ?? nr],
              [t("source"), t.has(`sourceTypes.${e.source_type}`) ? t(`sourceTypes.${e.source_type}`) : e.source_type],
              [t("note"), e.submitter_note ?? nr],
            ] as const
          ).map(([k, val]) => (
            <div key={String(k)} className="contents">
              <dt className="font-semibold">{k}</dt>
              <dd className="text-ink-2">{val}</dd>
            </div>
          ))}
        </dl>
        {e.lot_expiry_date ? (
          <p className="mt-3 text-sm text-ink-2">{t("lotExpired", { date: formatPartialDate(e.lot_expiry_date, "day", locale, nr) })}</p>
        ) : null}
        {e.submitted_at ? (
          <p className="mt-3 text-sm text-ink-2">
            {t("submitted", { date: formatDateTime(e.submitted_at, locale, ctx.tz) })}
            {e.submitted_by_name ? ` · ${e.submitted_by_name}` : ""}
          </p>
        ) : null}
      </Card>

      <Card>
        <h2 className="text-lg">{t("evidence")}</h2>
        {e.evidence.length === 0 ? (
          <p className="mt-2 text-ink-2">{t("noEvidence")}</p>
        ) : (
          <ul className="mt-3 grid gap-3 sm:grid-cols-2">
            {e.evidence.map((m) => (
              <li key={m.media_id} className="rounded-control border border-divider p-3">
                {m.url && m.detected_mime?.startsWith("image/") ? (
                  // eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL
                  <img src={m.url} alt={t("evidence")} className="mb-2 max-h-64 w-full rounded-md object-contain" />
                ) : (
                  <FileText aria-hidden className="mb-2 size-8 text-primary" />
                )}
                <p className="text-sm">{t.has(`evidenceStates.${m.state}`) ? t(`evidenceStates.${m.state}`) : m.state}</p>
                {m.url ? (
                  <a href={m.url} target="_blank" rel="noopener noreferrer" className="text-sm font-semibold">
                    {t("openEvidence")}
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <h2 className="text-lg">{t("reviews")}</h2>
        {e.reviews.length === 0 ? (
          <p className="mt-2 text-ink-2">{t("noReviews")}</p>
        ) : (
          <ol className="mt-3 space-y-3">
            {e.reviews.map((r) => (
              <li key={r.id} className="rounded-control border border-divider p-3">
                <p className="font-semibold">{t("reviewBy", { outcome: te(`state.${r.outcome}`), name: r.reviewer_name ?? "—" })}</p>
                <p className="text-sm text-ink-2">{formatDateTime(r.created_at, locale, ctx.tz)}</p>
                {r.reason ? <p className="mt-1">{r.reason}</p> : null}
              </li>
            ))}
          </ol>
        )}
      </Card>

      {e.state === "submitted" && ctx.can("vaccination.review") && !mine ? (
        <Button asChild variant="secondary">
          <Link href={`/app/review?id=${e.id}`}>{t("openReview")}</Link>
        </Button>
      ) : null}
    </PageBody>
  );
}
