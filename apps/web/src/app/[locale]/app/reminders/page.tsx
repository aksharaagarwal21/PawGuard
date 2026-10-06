import { BellOff } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { EmptyState, Notice } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { ReminderCard } from "@/components/pets/reminder-card";
import { pageContext } from "@/lib/page-context";

/** In-app vaccination reminders for the owner's pets (14, 7 and 1 day before, and overdue). Nothing is sent. */
export default async function RemindersPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  const t = await getTranslations("reminders");
  const { data, error } = await ctx.api.GET("/api/v1/my/reminders");
  const reminders = data ?? [];
  const petIds = [...new Set(reminders.map((r) => r.pet_id))];
  const options = await Promise.all(
    petIds.map((id) => ctx.api.GET("/api/v1/my/pets/{pet_id}/vaccine-options", { params: { path: { pet_id: id } } })),
  );
  const products = Object.fromEntries(petIds.map((id, i) => [id, options[i]?.data ?? []]));
  const realToday = new Date().toLocaleDateString("en-CA", { timeZone: ctx.tz });

  return (
    <PageBody>
      <PageHeader title={t("title")} intro={t("intro")} />
      <Notice tone="neutral">{t("inAppOnly")}</Notice>
      {error ? <Notice tone="urgent">{t("loadFailed")}</Notice> : null}
      {reminders.length === 0 && !error ? (
        <EmptyState icon={<BellOff aria-hidden className="size-6" />} title={t("emptyTitle")}>
          {t("emptyBody")}
        </EmptyState>
      ) : (
        <div className="space-y-8">
          {(
            [
              ["overdue", reminders.filter((r) => r.days_until_due < 0)],
              ["thisWeek", reminders.filter((r) => r.days_until_due >= 0 && r.days_until_due <= 7)],
              ["later", reminders.filter((r) => r.days_until_due > 7)],
            ] as const
          )
            .filter(([, list]) => list.length > 0)
            .map(([key, list]) => (
              <section key={key} aria-labelledby={`group-${key}`} className="space-y-3">
                <h2 id={`group-${key}`} className="text-lg">
                  {t(`groups.${key}`)} <span className="text-ink-2">({list.length})</span>
                </h2>
                <ul className="space-y-3">
                  {list.map((r) => (
                    <li key={r.id}>
                      <ReminderCard reminder={r} products={products[r.pet_id] ?? []} today={realToday} />
                    </li>
                  ))}
                </ul>
              </section>
            ))}
        </div>
      )}
    </PageBody>
  );
}
