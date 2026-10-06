import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Notice } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { AnimalThumb } from "@/components/prevention/evidence";
import { VaccinationForm } from "@/components/prevention/vaccination-form";
import { pageContext } from "@/lib/page-context";

export default async function NewVaccinationPage({ params }: { params: Promise<{ locale: string; id: string }> }) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  const t = await getTranslations("vaccForm");
  const te = await getTranslations("errors");
  const ta = await getTranslations("animal");
  if (!ctx.can("vaccination.submit")) {
    return (
      <PageBody>
        <Notice tone="urgent" title={te("forbiddenTitle")}>
          {te("forbiddenBody")}
        </Notice>
      </PageBody>
    );
  }
  const [{ data: animal }, { data: products }, { data: lots }, { data: areas }] = await Promise.all([
    ctx.api.GET("/api/v1/animals/{animal_id}", { params: { path: { animal_id: id } } }),
    ctx.api.GET("/api/v1/vaccine-products"),
    ctx.api.GET("/api/v1/vaccine-lots"),
    ctx.api.GET("/api/v1/areas"),
  ]);
  if (!animal) notFound();
  return (
    <PageBody>
      <PageHeader title={t("title")} back={{ href: `/app/animals/${animal.id}`, label: animal.reference_code }} />
      <div className="flex items-center gap-3 rounded-card border border-divider bg-surface p-3">
        <AnimalThumb url={animal.photo?.url} alt={animal.reference_code} size="sm" />
        <div>
          <p className="font-mono text-sm font-semibold">{animal.reference_code}</p>
          <p className="text-sm text-ink-2">
            {[animal.nickname ?? ta("noNickname"), animal.coat_description].filter(Boolean).join(" · ")}
          </p>
        </div>
      </div>
      <VaccinationForm
        animalId={animal.id}
        products={(products ?? []).map((p) => ({ id: p.id, name: p.name }))}
        lots={(lots ?? []).map((l) => ({ id: l.id, product_id: l.product_id, lot_number: l.lot_number }))}
        areas={(areas ?? []).map((a) => ({ id: a.id, name: a.name }))}
        initial={{ area_id: animal.home_area?.id ?? null }}
      />
    </PageBody>
  );
}
