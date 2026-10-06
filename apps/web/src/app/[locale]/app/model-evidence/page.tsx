import { getTranslations, setRequestLocale } from "next-intl/server";

import { Card, Notice, StatusChip } from "@pawguard/ui";

import evaluation from "@/content/pawid-evaluation.json";
import { PageBody, PageHeader } from "@/components/page-header";

type Metric = { value: number; ci95: [number, number] };
const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
const ci = (m: Metric) => `${pct(m.ci95[0])}–${pct(m.ci95[1])}`;

/** Measured evidence for the research-preview photo matching. Every number comes from the evaluation file. */
export default async function ModelEvidencePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("modelEvidence");
  const e = evaluation;
  const test = e.test as unknown as Record<string, Record<string, Metric>>;
  const head = test.pawid_dinov2s_head!;
  const c = e.dataset.counts;
  const sel = e.selection_on_validation;
  const closedRows = [
    ["pawid_dinov2s_head", t("methods.pawid")],
    ["dinov2s_backbone_cls", t("methods.backbone")],
    ["color_histogram", t("methods.histogram")],
    ["random", t("methods.random")],
  ] as const;
  const openRows = [
    ["fpir", t("open.fpir"), t("open.unknownCount", { q: c.test.unknown_queries, d: c.test.unknown_identities })],
    ["known_top1_correct_accepted", t("open.correct"), t("open.knownCount", { q: c.test.known_queries, d: c.test.known_identities })],
    ["false_rejection", t("open.rejected"), t("open.knownCount", { q: c.test.known_queries, d: c.test.known_identities })],
    ["known_top1_wrong_accepted", t("open.wrong"), t("open.knownCount", { q: c.test.known_queries, d: c.test.known_identities })],
  ] as const;
  return (
    <PageBody wide>
      <PageHeader title={t("title")} intro={t("intro")} />
      <Notice tone="pending" title={t("caveatTitle")}>
        <p className="font-semibold">{t("caveatLine")}</p>
        <p>{t("caveatBody")}</p>
      </Notice>
      <Card className="flex flex-wrap items-center gap-3">
        <StatusChip kind="submitted">{t("statusChip")}</StatusChip>
        <p className="text-sm">{t("status")}</p>
      </Card>

      <section aria-labelledby="what" className="space-y-2">
        <h2 id="what" className="text-lg">{t("whatTitle")}</h2>
        <p>
          {t("what", {
            known: c.test.known_identities,
            gallery: c.test.gallery_images,
            knownQ: c.test.known_queries,
            unknown: c.test.unknown_identities,
            unknownQ: c.test.unknown_queries,
            valDogs: c.validation.known_identities + c.validation.unknown_identities,
          })}
        </p>
        <p className="text-sm text-ink-2">{t("threshold", { tau: sel.threshold.toFixed(3), agg: sel.chosen_aggregation })}</p>
      </section>

      <section aria-labelledby="closed" className="space-y-2">
        <h2 id="closed" className="text-lg">{t("closedTitle")}</h2>
        <div className="overflow-x-auto rounded-control border border-divider" tabIndex={0} role="region" aria-labelledby="closed">
          <table className="w-full min-w-xl text-left text-sm">
            <thead>
              <tr className="border-b border-divider">
                <th scope="col" className="p-2">{t("colMethod")}</th>
                <th scope="col" className="p-2">{t("colTop1")}</th>
                <th scope="col" className="p-2">{t("colTop3")}</th>
                <th scope="col" className="p-2">{t("colMap")}</th>
              </tr>
            </thead>
            <tbody>
              {closedRows.map(([k, label]) => (
                <tr key={k} className="border-b border-divider">
                  <th scope="row" className="p-2 font-semibold">{label}</th>
                  {(["top1", "top3", "map_image"] as const).map((m) => (
                    <td key={m} className="p-2">
                      {pct(test[k]![m]!.value)} <span className="text-ink-2">({ci(test[k]![m]!)})</span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-sm text-ink-2">{t("closedNote", { q: c.test.known_queries, d: c.test.known_identities })}</p>
      </section>

      <section aria-labelledby="open" className="space-y-2">
        <h2 id="open" className="text-lg">{t("openTitle", { tau: sel.threshold.toFixed(3) })}</h2>
        <div className="overflow-x-auto rounded-control border border-divider" tabIndex={0} role="region" aria-labelledby="open">
          <table className="w-full min-w-xl text-left text-sm">
            <tbody>
              {openRows.map(([k, label, count]) => (
                <tr key={k} className="border-b border-divider">
                  <th scope="row" className="p-2 font-semibold">{label}</th>
                  <td className="p-2">
                    {pct(head[k]!.value)} <span className="text-ink-2">({ci(head[k]!)})</span>
                  </td>
                  <td className="p-2 text-ink-2">{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-sm">{t("openReading", { val: pct(sel.candidates.find((x) => x.aggregation === sel.chosen_aggregation)!.val_unknown_false_match), test: pct(head.fpir!.value) })}</p>
      </section>

      <section aria-labelledby="charts" className="grid gap-4 lg:grid-cols-2">
        <h2 id="charts" className="sr-only">{t("chartsTitle")}</h2>
        {/* eslint-disable-next-line @next/next/no-img-element -- static chart image */}
        <img src="/model-evidence/chart_top1_top3.png" alt={t("chart1Alt")} className="w-full rounded-control border border-divider bg-white" />
        {/* eslint-disable-next-line @next/next/no-img-element -- static chart image */}
        <img src="/model-evidence/chart_threshold_tradeoff.png" alt={t("chart2Alt")} className="w-full rounded-control border border-divider bg-white" />
      </section>

      <section aria-labelledby="limits" className="space-y-2">
        <h2 id="limits" className="text-lg">{t("limitsTitle")}</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>{t("limits.pet")}</li>
          <li>{t("limits.session")}</li>
          <li>{t("limits.small", { dogs: c.test.known_identities + c.test.unknown_identities })}</li>
          <li>{t("limits.threshold")}</li>
          <li>{t("limits.human")}</li>
        </ul>
      </section>

      <section aria-labelledby="repro" className="space-y-1 text-sm text-ink-2">
        <h2 id="repro" className="text-base text-ink">{t("reproTitle")}</h2>
        <p>{t("reproModel", { name: e.model.name, version: e.model.version_label })}</p>
        <p>{t("reproSplit", { hash: e.dataset.split_sha256.slice(0, 16), seed: e.seed, commit: e.commit.slice(0, 7) })}</p>
        <p>{t("reproTiming", { ms: e.timing.single_image_ms_median, search: e.timing.search_ms_per_query })}</p>
        <p className="font-mono">{e.command}</p>
      </section>
    </PageBody>
  );
}
