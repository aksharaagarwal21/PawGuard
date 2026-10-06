import { getTranslations, setRequestLocale } from "next-intl/server";

import { EmptyState, Notice } from "@pawguard/ui";

import { PageBody, PageHeader } from "@/components/page-header";
import { TaskCard } from "@/components/prevention/task-card";
import { Link } from "@/i18n/navigation";
import { pageContext } from "@/lib/page-context";

import { CreateTask } from "./create-task";

export default async function TasksPage({
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
  const t = await getTranslations("tasks");
  const te = await getTranslations("errors");
  const canManage = ctx.can("task.manage");
  if (!canManage && !ctx.can("task.work")) {
    return (
      <PageBody>
        <Notice tone="urgent" title={te("forbiddenTitle")}>
          {te("forbiddenBody")}
        </Notice>
      </PageBody>
    );
  }
  const showAll = canManage && sp.view === "all";
  const [{ data }, membersRes, areasRes] = await Promise.all([
    ctx.api.GET("/api/v1/tasks", { params: { query: { mine: !showAll, limit: 100 } } }),
    canManage ? ctx.api.GET("/api/v1/members") : Promise.resolve({ data: undefined }),
    canManage ? ctx.api.GET("/api/v1/areas") : Promise.resolve({ data: undefined }),
  ]);
  const members = (membersRes.data ?? []).filter((m) => m.can_work_tasks).map((m) => ({ membership_id: m.membership_id, name: m.name }));
  const items = data?.items ?? [];
  const open = items.filter((i) => !["completed", "cancelled"].includes(i.state));
  const closed = items.filter((i) => ["completed", "cancelled"].includes(i.state));
  return (
    <PageBody>
      <PageHeader
        title={t("title")}
        actions={canManage ? <CreateTask members={members} areas={(areasRes.data ?? []).map((a) => ({ id: a.id, name: a.name }))} /> : null}
      />
      {canManage ? (
        <nav aria-label={t("title")} className="flex gap-2">
          {(
            [
              ["mine", t("mine")],
              ["all", t("all")],
            ] as const
          ).map(([v, label]) => (
            <Link
              key={v}
              href={v === "all" ? "/app/tasks?view=all" : "/app/tasks"}
              aria-current={(v === "all") === showAll ? "page" : undefined}
              className={`inline-flex min-h-11 items-center rounded-full px-4 font-display text-sm font-semibold no-underline ${(v === "all") === showAll ? "bg-primary text-white" : "border border-control bg-surface text-ink"}`}
            >
              {label}
            </Link>
          ))}
        </nav>
      ) : null}
      {open.length === 0 && closed.length === 0 ? (
        <EmptyState title={t("empty")}>{showAll ? null : t("emptyMine")}</EmptyState>
      ) : (
        <>
          <ul className="space-y-3">
            {open.map((task) => (
              <TaskCard key={task.id} task={task} isMine={task.assignee_membership_id === ctx.active.membership_id} canManage={canManage} members={members} />
            ))}
          </ul>
          {closed.length ? (
            <details>
              <summary className="inline-flex min-h-11 cursor-pointer items-center font-display font-semibold">
                {t("states.completed")} / {t("states.cancelled")} ({closed.length})
              </summary>
              <ul className="mt-2 space-y-3">
                {closed.map((task) => (
                  <TaskCard key={task.id} task={task} isMine={task.assignee_membership_id === ctx.active.membership_id} canManage={canManage} members={members} />
                ))}
              </ul>
            </details>
          ) : null}
        </>
      )}
    </PageBody>
  );
}
