import { FileText } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Card, EmptyState, Notice, StatusChip } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { VaccinationStateChip } from "@/components/prevention/evidence";
import { EvidenceCheck } from "@/components/vaccinations/evidence-check";
import { Link } from "@/i18n/navigation";
import { formatDateTime, formatPartialDate } from "@/lib/format";
import { pageContext } from "@/lib/page-context";

import { ReviewActions } from "./review-actions";

export default async function ReviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const sp = await searchParams;
  const ctx = await pageContext();
  const t = await getTranslations("review");
  const tv = await getTranslations("vaccDetail");
  const tc = await getTranslations("common");
  const ta = await getTranslations("animal");
  if (!ctx.can("vaccination.review")) {
    return (
      <PageBody>
        <PageHeader title={t("title")} />
        <Notice tone="urgent" title={t("notAuthorised")} />
      </PageBody>
    );
  }
  const { data: queue } = await ctx.api.GET("/api/v1/vaccination-review-queue", { params: { query: { limit: 50 } } });
  const items = queue?.items ?? [];
  const selectedId = sp.id ?? items[0]?.id;
  const [{ data: e }] = selectedId
    ? await Promise.all([ctx.api.GET("/api/v1/vaccination-events/{event_id}", { params: { path: { event_id: selectedId } } })])
    : [{ data: undefined }];
  const [{ data: animal }, { data: others }, { data: drafts }] = e
    ? await Promise.all([
        ctx.api.GET("/api/v1/animals/{animal_id}", { params: { path: { animal_id: e.animal_id } } }),
        ctx.api.GET("/api/v1/vaccination-events", { params: { query: { animal_id: e.animal_id, limit: 20 } } }),
        ctx.api.GET("/api/v1/vaccination-events/{event_id}/certificate-drafts", { params: { path: { event_id: e.id } } }),
      ])
    : [{ data: undefined }, { data: undefined }, { data: undefined }];
  const draft = drafts?.[0];
  const fmtDay = (d: string | null | undefined) => formatPartialDate(d, "day", locale, nr);
  const nr = tc("notRecorded");
  const nextId = items.find((i) => i.id !== selectedId)?.id;

  return (
    <PageBody wide>
      <PageHeader title={t("title")} intro={t("intro")} />
      {sp.done ? (
        <Notice tone="success" title={t.has(`done.${sp.done}`) ? t(`done.${sp.done}`) : t("done.verified")} live="polite" />
      ) : null}
      {sp.stale ? <Notice tone="pending" title={t("staleRow")} live="polite" /> : null}
      {items.length === 0 && !e ? (
        <EmptyState title={t("empty")}>{t("emptyBody")}</EmptyState>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
          <section aria-labelledby="queue-h" className={sp.id ? "hidden lg:block" : undefined}>
            <h2 id="queue-h" className="text-base">
              {t("queue")} ({items.length})
            </h2>
            <ul className="mt-2 divide-y divide-divider rounded-card border border-divider bg-surface">
              {items.map((i) => (
                <li key={i.id}>
                  <Link
                    href={`/app/review?id=${i.id}`}
                    aria-current={i.id === selectedId ? "true" : undefined}
                    className={`block p-3 text-ink no-underline hover:bg-canvas ${i.id === selectedId ? "bg-sage" : ""}`}
                  >
                    <span className="font-mono text-sm font-semibold">{i.animal_reference}</span>
                    <span className="block text-sm text-ink-2">
                      {formatPartialDate(i.administered_on, i.date_precision, locale, nr)} · {i.submitted_by_name ?? "—"}
                    </span>
                    {i.has_conflict ? <StatusChip kind="disputed">{t("conflict")}</StatusChip> : null}
                  </Link>
                </li>
              ))}
            </ul>
          </section>

          {e ? (
            <section aria-labelledby="item-h" className={`space-y-4 ${sp.id ? "" : "hidden lg:block"}`}>
              {sp.id ? (
                <Link href="/app/review" className="inline-flex min-h-11 items-center font-semibold lg:hidden">
                  {t("backToQueue")}
                </Link>
              ) : null}
              <div className="flex flex-wrap items-center gap-2">
                <h2 id="item-h" className="text-xl">
                  {e.animal_reference}
                </h2>
                <VaccinationStateChip state={e.state} />
              </div>
              {e.conflicts.length ? (
                <Notice tone="pending" title={t("conflict")}>
                  <ul className="list-disc pl-5">
                    {e.conflicts.map((c) => (
                      <li key={c}>{tv.has(`conflictRules.${c}`) ? tv(`conflictRules.${c}`) : c}</li>
                    ))}
                  </ul>
                </Notice>
              ) : null}
              <div className="grid gap-4 xl:grid-cols-2">
                <Card>
                  <h3 className="text-base">{tv("evidence")}</h3>
                  {e.evidence.length === 0 ? (
                    <p className="mt-2 text-ink-2">{tv("noEvidence")}</p>
                  ) : (
                    <ul className="mt-2 space-y-3">
                      {e.evidence.map((m) => (
                        <li key={m.media_id}>
                          {m.url && m.detected_mime?.startsWith("image/") ? (
                            // eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL
                            <img src={m.url} alt={tv("evidence")} className="max-h-96 w-full rounded-md bg-canvas object-contain" />
                          ) : (
                            <FileText aria-hidden className="size-8 text-primary" />
                          )}
                          <p className="text-sm">
                            {tv.has(`evidenceStates.${m.state}`) ? tv(`evidenceStates.${m.state}`) : m.state}
                            {m.url ? (
                              <>
                                {" · "}
                                <a href={m.url} target="_blank" rel="noopener noreferrer">
                                  {tv("openEvidence")}
                                </a>
                              </>
                            ) : null}
                          </p>
                        </li>
                      ))}
                    </ul>
                  )}
                  {e.evidence.length ? (
                    <div className="mt-3">
                      <EvidenceCheck eventId={e.id} />
                    </div>
                  ) : null}
                  {draft ? (
                    <div className="mt-3 rounded-control border border-dashed border-control p-3 text-sm">
                      <p className="font-semibold">{tv("ocr.title")}</p>
                      <p className="text-ink-2">{tv("ocr.note")}</p>
                      <ul className="mt-1 list-disc pl-5">
                        <li>{tv("ocr.given", { date: draft.administered_on ? fmtDay(draft.administered_on) : "—" })}</li>
                        <li>{tv("ocr.vaccine", { name: draft.product_text ?? "—" })}</li>
                        <li>{tv("ocr.lot", { lot: draft.lot_text ?? "—" })}</li>
                        <li>{tv("ocr.nextDue", { date: draft.next_due_on ? fmtDay(draft.next_due_on) : "—" })}</li>
                      </ul>
                      {draft.confidence !== null && draft.confidence !== undefined ? (
                        <p className="text-xs text-ink-2">{tv("ocr.confidence", { pct: Math.round(draft.confidence * 100), engine: draft.engine })}</p>
                      ) : null}
                      {draft.warnings.map((w) => (
                        <p key={w} className="text-xs font-semibold">{w}</p>
                      ))}
                    </div>
                  ) : null}
                </Card>
                <Card>
                  <h3 className="text-base">{tv("title")}</h3>
                  {e.source_type === "owner_entry" ? (
                    <p className="mt-1 text-sm font-semibold">{tv("sourceTypes.owner_entry")}</p>
                  ) : null}
                  <dl className="mt-2 grid grid-cols-[9rem_1fr] gap-x-4 gap-y-1.5 text-sm">
                    {(
                      [
                        [tv("date"), formatPartialDate(e.administered_on, e.date_precision, locale, nr)],
                        [tv("product"), e.product_name ?? e.product_text ?? nr],
                        [tv("lot"), e.lot_number ?? e.lot_text ?? nr],
                        [tv("administeredBy"), e.administered_by_name ?? nr],
                        [tv("registration"), e.administered_by_registration ?? nr],
                        [tv("area"), e.area?.name ?? nr],
                        [tv("note"), e.submitter_note ?? nr],
                      ] as const
                    ).map(([k, v]) => (
                      <div key={k} className="contents">
                        <dt className="font-semibold">{k}</dt>
                        <dd className="text-ink-2">{v}</dd>
                      </div>
                    ))}
                  </dl>
                  {e.lot_expiry_date ? <p className="mt-2 text-sm">{tv("lotExpired", { date: formatPartialDate(e.lot_expiry_date, "day", locale, nr) })}</p> : null}
                  {e.submitted_at ? (
                    <p className="mt-2 text-sm text-ink-2">
                      {tv("submitted", { date: formatDateTime(e.submitted_at, locale, ctx.tz) })} · {e.submitted_by_name ?? "—"}
                    </p>
                  ) : null}
                  {animal ? (
                    <div className="mt-4 border-t border-divider pt-3 text-sm">
                      <p className="font-semibold">{tv("animal")}</p>
                      <p className="text-ink-2">
                        <Link href={`/app/animals/${animal.id}`}>{animal.reference_code}</Link> ·{" "}
                        {[animal.nickname ?? ta("noNickname"), animal.coat_description, animal.identifying_marks].filter(Boolean).join(" · ")}
                      </p>
                    </div>
                  ) : null}
                </Card>
              </div>
              <Card>
                <h3 className="text-base">{t("history")}</h3>
                {(others?.items ?? []).filter((o) => o.id !== e.id).length === 0 ? (
                  <p className="mt-2 text-ink-2">{t("noHistory")}</p>
                ) : (
                  <ul className="mt-2 space-y-1 text-sm">
                    {(others?.items ?? [])
                      .filter((o) => o.id !== e.id)
                      .map((o) => (
                        <li key={o.id} className="flex flex-wrap items-center gap-2">
                          <Link href={`/app/vaccinations/${o.id}`}>{formatPartialDate(o.administered_on, o.date_precision, locale, nr)}</Link>
                          <span className="text-ink-2">{o.product_name ?? o.product_text ?? nr}</span>
                          <VaccinationStateChip state={o.state} />
                        </li>
                      ))}
                  </ul>
                )}
              </Card>
              {e.state === "submitted" ? (
                <ReviewActions eventId={e.id} rowVersion={e.row_version} nextId={nextId} suggestedNextDue={draft?.next_due_on ?? null} />
              ) : null}
            </section>
          ) : (
            <p className="text-ink-2">{t("select")}</p>
          )}
        </div>
      )}
    </PageBody>
  );
}
