import { Bell, Plus } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button, Card, EmptyState, Notice, StatusChip } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { NextDueLine, PetAvatar, PetStatusChip } from "@/components/pets/status";
import { Link } from "@/i18n/navigation";
import { pageContext } from "@/lib/page-context";

/** "My pets": only pets linked to the signed-in owner, with one vaccination status each. */
export default async function MyPetsPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  const t = await getTranslations("pets");
  const [petsRes, remindersRes] = await Promise.all([
    ctx.api.GET("/api/v1/my/pets"),
    ctx.api.GET("/api/v1/my/reminders"),
  ]);
  const pets = petsRes.data ?? [];
  const reminders = remindersRes.data ?? [];

  return (
    <PageBody>
      <PageHeader
        title={t("title")}
        intro={t("intro")}
        actions={
          <Button asChild>
            <Link href="/app/pets/new">
              <Plus aria-hidden className="size-5" />
              {t("addPet")}
            </Link>
          </Button>
        }
      />
      {petsRes.error ? <Notice tone="urgent">{t("loadFailed")}</Notice> : null}
      {reminders.length > 0 ? (
        <Notice tone="pending" title={t("remindersWaiting", { count: reminders.length })}>
          <p>
            <Link href="/app/reminders">
              <Bell aria-hidden className="mr-1 inline size-4" />
              {t("openReminders")}
            </Link>
          </p>
        </Notice>
      ) : null}
      {pets.length === 0 && !petsRes.error ? (
        <EmptyState
          title={t("emptyTitle")}
          action={
            <Button asChild>
              <Link href="/app/pets/new">{t("addPet")}</Link>
            </Button>
          }
        >
          {t("emptyBody")}
        </EmptyState>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2" aria-label={t("listLabel")}>
          {pets.map((p) => (
            <li key={p.id}>
              <Card className="h-full p-0">
                <Link href={`/app/pets/${p.id}`} className="flex h-full gap-3 p-4 text-ink no-underline hover:bg-sage/40">
                  <PetAvatar url={p.photo_url} name={p.name} />
                  <div className="min-w-0 flex-1 space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-display text-lg font-semibold">{p.name}</span>
                      {p.is_demo ? <StatusChip kind="demo">{t("demoData")}</StatusChip> : null}
                    </div>
                    <p className="text-sm text-ink-2">
                      {t(`species.${p.species as "dog" | "cat"}`)} · {p.clinic_name}
                    </p>
                    <PetStatusChip status={p.status} />
                    <NextDueLine status={p.status} />
                    {p.awaiting_verification > 0 ? (
                      <p className="text-sm text-ink-2">{t("awaiting", { count: p.awaiting_verification })}</p>
                    ) : null}
                  </div>
                </Link>
              </Card>
            </li>
          ))}
        </ul>
      )}
      <p className="text-sm text-ink-2">{t("remindOnly")}</p>
    </PageBody>
  );
}
