import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button, Card, Notice } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { AnimalThumb } from "@/components/prevention/evidence";
import { Link } from "@/i18n/navigation";
import { pageContext } from "@/lib/page-context";

import { PhotoLookup } from "./photo-lookup";
import { SightingForm } from "./sighting-form";

/**
 * Capture entry point. With ?animal=… it records a sighting (optionally with a photo) for that animal.
 * Without one, it offers photo lookup only when the API reports a usable identity model (assisted, or a labelled
 * research preview in demo organisations); otherwise it says plainly that matching is not available. The manual
 * paths are always shown.
 */
export default async function CapturePage({
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
  const t = await getTranslations("capture");
  const ta = await getTranslations("animal");
  const te = await getTranslations("errors");
  if (!ctx.can("observation.write")) {
    return (
      <PageBody>
        <Notice tone="urgent" title={te("forbiddenTitle")}>
          {te("forbiddenBody")}
        </Notice>
      </PageBody>
    );
  }
  if (!sp.animal) {
    const status = ctx.can("identity.search") ? (await ctx.api.GET("/api/v1/identity/status")).data : undefined;
    const lookup = status && status.mode !== "unavailable" && ctx.can("media.upload") ? status.mode : null;
    const ti = await getTranslations("identity");
    return (
      <PageBody>
        <PageHeader title={lookup ? t("lookupTitle") : t("title")} intro={lookup ? t("lookupIntro") : t("intro")} />
        {lookup ? (
          <PhotoLookup mode={lookup} canRegister={ctx.can("animal.write")} />
        ) : (
          <Notice tone="info" title={t("matchingUnavailableTitle")}>
            <p>{t("matchingUnavailableBody")}</p>
            {status?.reason === "research_only" ? <p>{ti("researchOnly")}</p> : null}
          </Notice>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Button asChild size="lg" block>
            <Link href="/app/animals">{t("findFirst")}</Link>
          </Button>
          {ctx.can("animal.write") ? (
            <Button asChild size="lg" variant="secondary" block>
              <Link href="/app/animals/new">{t("registerNew")}</Link>
            </Button>
          ) : null}
        </div>
      </PageBody>
    );
  }
  const [{ data: animal }, { data: areas }] = await Promise.all([
    ctx.api.GET("/api/v1/animals/{animal_id}", { params: { path: { animal_id: sp.animal } } }),
    ctx.api.GET("/api/v1/areas"),
  ]);
  if (!animal) {
    return (
      <PageBody>
        <Notice tone="urgent" title={te("notFoundTitle")}>
          {te("notFoundBody")}
        </Notice>
      </PageBody>
    );
  }
  return (
    <PageBody>
      <PageHeader title={t("sightingTitle")} back={{ href: `/app/animals/${animal.id}`, label: animal.reference_code }} />
      <Card className="flex items-center gap-3">
        <AnimalThumb url={animal.photo?.url} alt={animal.reference_code} size="sm" />
        <div>
          <p className="font-mono text-sm font-semibold">{animal.reference_code}</p>
          <p className="text-sm text-ink-2">{[animal.nickname ?? ta("noNickname"), animal.coat_description].filter(Boolean).join(" · ")}</p>
        </div>
      </Card>
      <SightingForm
        animalId={animal.id}
        defaultArea={animal.home_area?.id ?? ""}
        areas={(areas ?? []).map((a) => ({ id: a.id, name: a.name }))}
        canUpload={ctx.can("media.upload")}
      />
    </PageBody>
  );
}
