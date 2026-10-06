import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Notice } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { VaccinationForm } from "@/components/prevention/vaccination-form";
import { pageContext } from "@/lib/page-context";

export default async function AmendVaccinationPage({ params }: { params: Promise<{ locale: string; id: string }> }) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  const t = await getTranslations("vaccForm");
  const te = await getTranslations("errors");
  const [{ data: e }, { data: products }, { data: lots }, { data: areas }] = await Promise.all([
    ctx.api.GET("/api/v1/vaccination-events/{event_id}", { params: { path: { event_id: id } } }),
    ctx.api.GET("/api/v1/vaccine-products"),
    ctx.api.GET("/api/v1/vaccine-lots"),
    ctx.api.GET("/api/v1/areas"),
  ]);
  if (!e) notFound();
  const allowed = (e.submitted_by === ctx.me.user_id || ctx.can("task.manage")) && ["needs_correction", "draft"].includes(e.state);
  if (!allowed) {
    return (
      <PageBody>
        <Notice tone="urgent" title={te("forbiddenTitle")}>
          {te("forbiddenBody")}
        </Notice>
      </PageBody>
    );
  }
  const reason = e.reviews.at(-1)?.reason;
  return (
    <PageBody>
      <PageHeader title={t("amendTitle")} intro={t("forAnimal", { reference: e.animal_reference })} back={{ href: `/app/vaccinations/${e.id}`, label: t("amendTitle") }} />
      {reason ? <Notice tone="pending" title={t("reviewerReason", { reason })} /> : null}
      <VaccinationForm
        animalId={e.animal_id}
        products={(products ?? []).map((p) => ({ id: p.id, name: p.name }))}
        lots={(lots ?? []).map((l) => ({ id: l.id, product_id: l.product_id, lot_number: l.lot_number }))}
        areas={(areas ?? []).map((a) => ({ id: a.id, name: a.name }))}
        amend={{ eventId: e.id, rowVersion: e.row_version }}
        initial={e}
      />
    </PageBody>
  );
}
