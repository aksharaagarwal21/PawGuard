import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Card, Notice, StatusChip } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { Link } from "@/i18n/navigation";
import { formatDateTime } from "@/lib/format";
import { pageContext } from "@/lib/page-context";

import { MergeDecision } from "./merge-decision";

export default async function MergeDetailPage({
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
  const t = await getTranslations("merge");
  const { data: m } = await ctx.api.GET("/api/v1/animal-merges/{merge_id}", { params: { path: { merge_id: id } } });
  if (!m) notFound();
  const moved = Object.entries(m.moved)
    .map(([k, v]) => `${t.has(`moves.${k}`) ? t(`moves.${k}`) : k}: ${v}`)
    .join(", ");
  const mine = m.proposed_by === ctx.me.user_id;
  return (
    <PageBody>
      {sp.proposed ? <Notice tone="success" title={t("proposed")} live="polite" /> : null}
      <PageHeader title={t("detailTitle", { source: m.source_reference, target: m.target_reference })} back={{ href: "/app/merges", label: t("title") }}>
        <StatusChip kind={m.state === "executed" ? "verified" : m.state === "proposed" ? "submitted" : "neutral"}>{t(`states.${m.state}`)}</StatusChip>
      </PageHeader>
      <Card className="space-y-2">
        <p>
          <Link href={`/app/animals/${m.source_animal_id}`}>{m.source_reference}</Link> →{" "}
          <Link href={`/app/animals/${m.target_animal_id}`}>{m.target_reference}</Link>
        </p>
        <p className="text-ink-2">{m.reason}</p>
        <p className="text-sm text-ink-2">{formatDateTime(m.created_at, locale, ctx.tz)}</p>
        {moved ? <p className="text-sm">{t("moved", { summary: moved })}</p> : null}
        {m.reversal_reason ? <p className="text-sm">{m.reversal_reason}</p> : null}
      </Card>
      {m.state === "proposed" && mine ? <Notice tone="info" title={t("secondPerson")} /> : null}
      {ctx.can("animal.merge") && ((m.state === "proposed" && !mine) || m.state === "executed") ? (
        <MergeDecision mergeId={m.id} state={m.state} />
      ) : null}
    </PageBody>
  );
}
