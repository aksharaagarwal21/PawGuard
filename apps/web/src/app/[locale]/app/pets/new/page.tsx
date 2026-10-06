import { getTranslations, setRequestLocale } from "next-intl/server";

import { Notice } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { PetForm } from "@/components/pets/pet-form";
import { pageContext } from "@/lib/page-context";

export default async function NewPetPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  const t = await getTranslations("pets");
  const { data: clinics } = await ctx.api.GET("/api/v1/my/clinics");
  const today = new Date().toLocaleDateString("en-CA", { timeZone: ctx.tz }); // calendar date in the clinic's zone
  return (
    <PageBody>
      <PageHeader title={t("form.title")} intro={t("form.intro")} back={{ href: "/app/pets", label: t("title") }} />
      {clinics && clinics.length > 0 ? (
        <PetForm clinics={clinics} today={today} />
      ) : (
        <Notice tone="info">{t("form.noClinic")}</Notice>
      )}
    </PageBody>
  );
}
