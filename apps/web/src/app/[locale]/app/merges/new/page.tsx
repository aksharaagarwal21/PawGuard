import type { Schemas } from "@pawguard/api-client";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button, Card, Notice } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { AnimalThumb, ProfileStateChip, VaccinationSummaryChip } from "@/components/prevention/evidence";
import { pageContext } from "@/lib/page-context";

import { ProposeMerge } from "./propose-merge";

type Animal = Schemas["AnimalOut"];

export default async function NewMergePage({
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
  const t = await getTranslations("merge");
  if (!sp.source) notFound();
  const { data: source } = await ctx.api.GET("/api/v1/animals/{animal_id}", { params: { path: { animal_id: sp.source } } });
  if (!source) notFound();

  let targetId: string | null = null;
  let notFoundRef = false;
  const ref = sp.target?.trim().toUpperCase();
  if (ref) {
    const { data: found } = await ctx.api.GET("/api/v1/animals", { params: { query: { q: ref, limit: 5 } } });
    const match = found?.items.find((a) => a.reference_code === ref && a.id !== source.id);
    if (match) targetId = match.id;
    else notFoundRef = true;
  }
  const preview = targetId
    ? (
        await ctx.api.POST("/api/v1/animal-merges/preview", {
          body: { source_animal_id: source.id, target_animal_id: targetId, reason: "preview" },
        })
      ).data
    : undefined;

  return (
    <PageBody wide>
      <PageHeader title={t("title")} intro={t("intro")} back={{ href: `/app/animals/${source.id}`, label: source.reference_code }} />
      <form method="get" className="flex flex-wrap items-end gap-2 rounded-card border border-divider bg-surface p-4">
        <input type="hidden" name="source" value={source.id} />
        <label className="min-w-0 flex-1">
          <span className="font-display text-sm font-semibold">{t("findTarget")}</span>
          <input name="target" defaultValue={sp.target ?? ""} placeholder="PG-XXXX-XXXX" className="mt-1 min-h-11 w-full rounded-control border border-control px-3 font-mono" />
        </label>
        <Button type="submit">{t("preview")}</Button>
      </form>
      {notFoundRef ? <Notice tone="pending" title={t("notFound")} /> : null}

      {preview ? (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <Side title={t("source")} animal={preview.source} />
            <Side title={t("target")} animal={preview.target} />
          </div>
          <Card>
            <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {Object.entries(preview.moves).map(([k, v]) => (
                <div key={k}>
                  <dt className="text-sm text-ink-2">{t.has(`moves.${k}`) ? t(`moves.${k}`) : k}</dt>
                  <dd className="font-display text-xl font-bold">{v}</dd>
                </div>
              ))}
            </dl>
            <h2 className="mt-4 text-base">{t("conflicts")}</h2>
            {preview.conflicts.length ? (
              <ul className="mt-1 list-disc pl-5">
                {preview.conflicts.map((c) => (
                  <li key={c}>{t.has(`conflictLabels.${c}`) ? t(`conflictLabels.${c}`) : c}</li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-ink-2">{t("noConflicts")}</p>
            )}
          </Card>
          <ProposeMerge sourceId={preview.source.id} targetId={preview.target.id} />
        </>
      ) : null}
    </PageBody>
  );
}

async function Side({ title, animal }: { title: string; animal: Animal }) {
  const ta = await getTranslations("animal");
  const tc = await getTranslations("common");
  return (
    <Card className="space-y-3">
      <h2 className="text-base">{title}</h2>
      <div className="flex items-center gap-3">
        <AnimalThumb url={animal.photo?.url} alt={animal.reference_code} />
        <div>
          <p className="font-mono font-semibold">{animal.reference_code}</p>
          <p className="text-sm">{animal.nickname ?? ta("noNickname")}</p>
          <div className="mt-1 flex flex-wrap gap-1">
            <ProfileStateChip state={animal.profile_state} />
            <VaccinationSummaryChip summary={animal.vaccination} />
          </div>
        </div>
      </div>
      <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-1 text-sm">
        {(
          [
            [ta("sex.label"), ta(`sex.${animal.sex}`)],
            [ta("sterilisation.label"), ta(`sterilisation.${animal.sterilisation_status}`)],
            [ta("ageBand.label"), ta(`ageBand.${animal.age_band}`)],
            [ta("coat"), animal.coat_description ?? tc("notRecorded")],
            [ta("marks"), animal.identifying_marks ?? tc("notRecorded")],
            [ta("homeArea"), animal.home_area?.name ?? tc("notRecorded")],
          ] as const
        ).map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="font-semibold">{k}</dt>
            <dd className="text-ink-2">{v}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
