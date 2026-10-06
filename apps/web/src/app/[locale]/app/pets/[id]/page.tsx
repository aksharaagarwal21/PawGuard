import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { Card, Notice, StatusChip } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { OwnerRecordForm } from "@/components/pets/owner-record-form";
import { ReminderCard } from "@/components/pets/reminder-card";
import { DueSource, NextDueLine, PetAvatar, PetStatusChip, VerificationChip } from "@/components/pets/status";
import { formatPartialDate } from "@/lib/format";
import { pageContext } from "@/lib/page-context";

export default async function PetPage({ params }: { params: Promise<{ locale: string; id: string }> }) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  const t = await getTranslations("pets");
  const tc = await getTranslations("common");
  const [petRes, productsRes] = await Promise.all([
    ctx.api.GET("/api/v1/my/pets/{pet_id}", { params: { path: { pet_id: id } } }),
    ctx.api.GET("/api/v1/my/pets/{pet_id}/vaccine-options", { params: { path: { pet_id: id } } }),
  ]);
  if (petRes.response.status === 404 || petRes.response.status === 422) notFound();
  const pet = petRes.data;
  if (!pet) return <PageBody><Notice tone="urgent">{t("loadFailed")}</Notice></PageBody>;
  const products = productsRes.data ?? [];
  const realToday = new Date().toLocaleDateString("en-CA", { timeZone: ctx.tz });
  const fmt = (d: string | null | undefined) => formatPartialDate(d, "day", locale, tc("notRecorded"));

  return (
    <PageBody>
      <PageHeader
        title={pet.name}
        back={{ href: "/app/pets", label: t("title") }}
      />
      {pet.demo_offset_days !== 0 ? (
        <Notice tone="neutral">{t("demoDate", { date: fmt(pet.today), days: pet.demo_offset_days })}</Notice>
      ) : null}

      <Card className="flex flex-wrap gap-4">
        <PetAvatar url={pet.photo_url} name={pet.name} size="lg" />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <PetStatusChip status={pet.status} />
            {pet.is_demo ? <StatusChip kind="demo">{t("demoData")}</StatusChip> : null}
          </div>
          <NextDueLine status={pet.status} />
          {pet.awaiting_verification > 0 ? (
            <p className="text-sm text-ink-2">{t("awaiting", { count: pet.awaiting_verification })}</p>
          ) : null}
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
            <dt className="text-ink-2">{t("speciesLabel")}</dt>
            <dd>{t(`species.${pet.species as "dog" | "cat"}`)}</dd>
            <dt className="text-ink-2">{t("dobLabel")}</dt>
            <dd>{fmt(pet.date_of_birth)}</dd>
            <dt className="text-ink-2">{t("clinicLabel")}</dt>
            <dd>{pet.clinic_name}</dd>
            <dt className="text-ink-2">{t("referenceLabel")}</dt>
            <dd className="font-mono">{pet.reference_code}</dd>
          </dl>
        </div>
      </Card>

      {pet.reminders.length > 0 ? (
        <section aria-labelledby="pet-reminders" className="space-y-3">
          <h2 id="pet-reminders" className="text-lg">{t("remindersTitle")}</h2>
          {pet.reminders.map((r) => (
            <ReminderCard key={r.id} reminder={r} products={products} today={realToday} showPet={false} />
          ))}
        </section>
      ) : null}

      <section aria-labelledby="timeline" className="space-y-3">
        <h2 id="timeline" className="text-lg">{t("timelineTitle")}</h2>
        {pet.timeline.length === 0 ? (
          <p className="text-ink-2">{t("timelineEmpty")}</p>
        ) : (
          <ol className="space-y-3">
            {pet.timeline.map((e) => (
              <li key={e.event_id}>
                <Card className="space-y-1.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-display font-semibold">{e.vaccine}</p>
                    <VerificationChip value={e.verification} />
                  </div>
                  <p className="text-sm">
                    {t("givenOn", { date: fmt(e.administered_on) })} · {e.clinic_name}
                    {e.given_by ? ` · ${e.given_by}` : ""}
                  </p>
                  {e.next_due_on ? (
                    <div className="text-sm">
                      <p>{t("nextDue", { date: fmt(e.next_due_on) })}</p>
                      <DueSource source={e.next_due_source} />
                    </div>
                  ) : null}
                  {e.certificates > 0 ? <p className="text-sm text-ink-2">{t("certificates", { count: e.certificates })}</p> : null}
                  {e.note ? <p className="text-sm font-semibold">{t("clinicNote", { note: e.note })}</p> : null}
                </Card>
              </li>
            ))}
          </ol>
        )}
      </section>

      <details className="rounded-card border border-divider bg-surface p-4">
        <summary className="cursor-pointer font-display font-semibold">{t("addPast")}</summary>
        <div className="mt-3">
          <OwnerRecordForm petId={pet.id} clinicOrgId={pet.clinic_org_id} products={products} today={realToday} />
        </div>
      </details>
      <p className="text-sm text-ink-2">{t("remindOnly")}</p>
    </PageBody>
  );
}
