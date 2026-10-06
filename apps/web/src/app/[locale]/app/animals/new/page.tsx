import { getTranslations, setRequestLocale } from "next-intl/server";

import { Notice } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { pageContext } from "@/lib/page-context";

import { NewAnimalForm } from "./new-animal-form";

export default async function NewAnimalPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  const t = await getTranslations("animalForm");
  const tn = await getTranslations("nav");
  const te = await getTranslations("errors");
  if (!ctx.can("animal.write")) {
    return (
      <PageBody>
        <Notice tone="urgent" title={te("forbiddenTitle")}>
          {te("forbiddenBody")}
        </Notice>
      </PageBody>
    );
  }
  const { data: areas } = await ctx.api.GET("/api/v1/areas");
  return (
    <PageBody>
      <PageHeader title={t("title")} back={{ href: "/app/animals", label: tn("animals") }} />
      <NewAnimalForm areas={(areas ?? []).map((a) => ({ id: a.id, name: a.name }))} canUpload={ctx.can("media.upload")} />
    </PageBody>
  );
}
