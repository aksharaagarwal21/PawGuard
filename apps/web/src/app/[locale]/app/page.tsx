import { ClipboardList, Plus, Search } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button, EmptyState, Notice } from "@pawguard/ui";

import { PageBody } from "@/components/page-header";
import { VaccinationStateChip } from "@/components/prevention/evidence";
import { TaskCard } from "@/components/prevention/task-card";
import { Link, redirect } from "@/i18n/navigation";
import { formatPartialDate } from "@/lib/format";
import { STAFF_CAPS } from "@/lib/nav";
import { pageContext } from "@/lib/page-context";

export default async function TodayPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  if (ctx.can("pet.own") && !STAFF_CAPS.some((c) => ctx.can(c))) {
    redirect({ href: "/app/pets", locale }); // pet owners start at "My pets"
  }
  const t = await getTranslations("today");
  const tr = await getTranslations("roles");
  const tc = await getTranslations("common");
  const canWork = ctx.can("task.work") || ctx.can("task.manage");
  const canSubmit = ctx.can("vaccination.submit");
  const [tasksRes, correctionsRes, recentRes, queueRes] = await Promise.all([
    canWork
      ? ctx.api.GET("/api/v1/tasks", { params: { query: { mine: true, state: ["assigned", "in_progress", "blocked"], limit: 5 } } })
      : Promise.resolve({ data: undefined }),
    canSubmit
      ? ctx.api.GET("/api/v1/vaccination-events", { params: { query: { submitted_by_me: true, state: ["needs_correction"], limit: 10 } } })
      : Promise.resolve({ data: undefined }),
    canSubmit
      ? ctx.api.GET("/api/v1/vaccination-events", { params: { query: { submitted_by_me: true, limit: 5 } } })
      : Promise.resolve({ data: undefined }),
    ctx.can("vaccination.review")
      ? ctx.api.GET("/api/v1/vaccination-review-queue", { params: { query: { limit: 100 } } })
      : Promise.resolve({ data: undefined }),
  ]);
  const mergesRes = ctx.can("animal.merge")
    ? await ctx.api.GET("/api/v1/animal-merges", { params: { query: { state: "proposed" } } })
    : { data: undefined };
  const pendingMerges = (mergesRes.data ?? []).filter((m) => m.proposed_by !== ctx.me.user_id).length;
  const name = ctx.me.preferred_name;
  const tasks = tasksRes.data?.items ?? [];
  const corrections = correctionsRes.data?.items ?? [];
  const recent = recentRes.data?.items ?? [];
  const waiting = queueRes.data?.items.length ?? 0;

  return (
    <PageBody>
      <div>
        <h1 className="text-2xl">{name ? t("greeting", { name }) : t("greetingNoName")}</h1>
        <p className="mt-1 text-ink-2">
          {ctx.active.org_name} · {t("roleLabel")}: {tr(ctx.active.role)}
        </p>
      </div>

      {ctx.can("animal.read") ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Button asChild size="lg" block>
            <Link href="/app/animals">
              <Search aria-hidden className="size-5" />
              {t("findAnimal")}
            </Link>
          </Button>
          {ctx.can("animal.write") ? (
            <Button asChild size="lg" variant="secondary" block>
              <Link href="/app/animals/new">
                <Plus aria-hidden className="size-5" />
                {t("addAnimal")}
              </Link>
            </Button>
          ) : null}
        </div>
      ) : null}

      {waiting > 0 ? (
        <Notice tone="pending" title={t("reviewWaiting", { count: waiting })}>
          <p>
            <Link href="/app/review">{t("openWorkbench")}</Link>
          </p>
        </Notice>
      ) : null}

      {pendingMerges > 0 ? (
        <Notice tone="pending" title={t("mergesWaiting", { count: pendingMerges })}>
          <p>
            <Link href="/app/merges">{t("openMerges")}</Link>
          </p>
        </Notice>
      ) : null}

      {corrections.length ? (
        <section aria-labelledby="corrections-h" className="space-y-2">
          <h2 id="corrections-h" className="text-lg">
            {t("correctionsTitle")}
          </h2>
          <ul className="space-y-2">
            {corrections.map((e) => (
              <li key={e.id} className="rounded-card border-l-4 border-urgent bg-surface p-3">
                <Link href={`/app/vaccinations/${e.id}`} className="font-display font-semibold">
                  {e.animal_reference}
                </Link>
                <p className="text-sm text-ink-2">{formatPartialDate(e.administered_on, e.date_precision, locale, tc("notRecorded"))}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {canWork ? (
        <section aria-labelledby="tasks-heading" className="space-y-2">
          <div className="flex items-baseline justify-between gap-2">
            <h2 id="tasks-heading" className="text-lg">
              {t("tasksTitle")}
            </h2>
            <Link href="/app/tasks" className="text-sm font-semibold">
              {t("viewAllTasks")}
            </Link>
          </div>
          {tasks.length ? (
            <ul className="space-y-3">
              {tasks.map((task) => (
                <TaskCard key={task.id} task={task} isMine canManage={ctx.can("task.manage")} />
              ))}
            </ul>
          ) : (
            <EmptyState icon={<ClipboardList aria-hidden className="size-6" />} title={t("noTasksTitle")}>
              {t("noTasksBody")}
            </EmptyState>
          )}
        </section>
      ) : null}

      {canSubmit ? (
        <section aria-labelledby="recent-h" className="space-y-2">
          <h2 id="recent-h" className="text-lg">
            {t("submissionsTitle")}
          </h2>
          {recent.length ? (
            <ul className="divide-y divide-divider rounded-card border border-divider bg-surface">
              {recent.map((e) => (
                <li key={e.id}>
                  <Link href={`/app/vaccinations/${e.id}`} className="flex flex-wrap items-center justify-between gap-2 p-3 text-ink no-underline hover:bg-canvas">
                    <span>
                      <span className="font-mono text-sm font-semibold">{e.animal_reference}</span>
                      <span className="block text-sm text-ink-2">{formatPartialDate(e.administered_on, e.date_precision, locale, tc("notRecorded"))}</span>
                    </span>
                    <VaccinationStateChip state={e.state} />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-ink-2">{t("noSubmissions")}</p>
          )}
        </section>
      ) : null}
    </PageBody>
  );
}
