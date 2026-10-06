"use client";

import type { Schemas } from "@pawguard/api-client";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { Button, Dialog, Field, Select, StatusChip, Textarea, useToast } from "@pawguard/ui";

import { Link, useRouter } from "@/i18n/navigation";
import { browserApi, parseApiError } from "@/lib/api-browser";
import { formatPartialDate } from "@/lib/format";

type Task = Schemas["TaskOut"];
type Action = "start" | "complete" | "block" | "assign" | "cancel" | "reopen";
type Member = { membership_id: string; name: string | null };

const STATE_CHIP = { unassigned: "neutral", assigned: "neutral", in_progress: "submitted", completed: "verified", blocked: "disputed", cancelled: "superseded" } as const;

export function TaskCard({
  task,
  isMine,
  canManage,
  members,
}: {
  task: Task;
  isMine: boolean;
  canManage: boolean;
  members?: Member[];
}) {
  const t = useTranslations("tasks");
  const tc = useTranslations("common");
  const locale = useLocale();
  const router = useRouter();
  const toast = useToast();
  const [action, setAction] = useState<Action | null>(null);
  const [note, setNote] = useState("");
  const [assignee, setAssignee] = useState(task.assignee_membership_id ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const available: Action[] = [];
  const s = task.state;
  if ((isMine || canManage) && ["assigned", "blocked"].includes(s)) available.push("start");
  if ((isMine || canManage) && ["assigned", "in_progress"].includes(s)) available.push("complete", "block");
  if (canManage && ["unassigned", "assigned", "blocked"].includes(s)) available.push("assign");
  if (canManage && ["unassigned", "assigned", "in_progress", "blocked"].includes(s)) available.push("cancel");
  if (canManage && ["completed", "cancelled"].includes(s)) available.push("reopen");

  async function run(a: Action) {
    const needsReason = a === "block" || a === "cancel";
    if (needsReason && note.trim().length < 3) return setError(tc("reasonRequired"));
    if (a === "assign" && !assignee) return setError(t("assignee"));
    setBusy(true);
    const { error: apiError } = await browserApi.POST("/api/v1/tasks/{task_id}/transitions", {
      params: { path: { task_id: task.id } },
      body: { action: a, note: note.trim() || null, assignee_membership_id: a === "assign" ? assignee : null, row_version: task.row_version },
    });
    setBusy(false);
    if (apiError) {
      const p = parseApiError(apiError);
      return setError(p.code === "stale_row_version" ? tc("changedElsewhere") : p.fields.note || p.message);
    }
    setAction(null);
    setNote("");
    toast({ title: t("updated"), tone: "success" });
    router.refresh();
  }

  const direct = (a: Action) => a === "start" || a === "reopen";
  return (
    <li className="space-y-2 rounded-card border border-divider bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-display font-semibold">{task.title}</p>
          <p className="text-sm text-ink-2">
            {[
              t(`types.${task.task_type}`),
              task.area?.name,
              task.due_on ? t("dueOn", { date: formatPartialDate(task.due_on, "day", locale, "") }) : null,
              task.priority !== "normal" ? t(`priority.${task.priority}`) : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <StatusChip kind={STATE_CHIP[s]}>{t(`states.${s}`)}</StatusChip>
      </div>
      {task.instructions ? <p className="text-sm">{task.instructions}</p> : null}
      {task.priority_rationale ? <p className="text-sm text-ink-2">{task.priority_rationale}</p> : null}
      {task.blocked_reason && s === "blocked" ? <p className="text-sm font-semibold">{t("blockedBecause", { reason: task.blocked_reason })}</p> : null}
      <div className="flex flex-wrap gap-2 text-sm">
        {task.animal_id ? <Link href={`/app/animals/${task.animal_id}`}>{t("animal", { reference: task.animal_reference ?? "" })}</Link> : null}
        {task.source_event_type === "vaccination_event" && task.source_event_id ? (
          <Link href={`/app/vaccinations/${task.source_event_id}`}>{tc("view")}</Link>
        ) : null}
        {task.task_type === "survey" && task.area && !["completed", "cancelled"].includes(s) ? (
          <Link href={`/app/surveys/new?area=${task.area.id}&task=${task.id}${task.campaign_id ? `&campaign=${task.campaign_id}` : ""}`}>{t("recordCount")}</Link>
        ) : null}
        {canManage ? <span className="text-ink-2">{task.assignee_name ?? t("unassigned")}</span> : null}
      </div>
      {available.length ? (
        <div className="flex flex-wrap gap-2">
          {available.map((a) => (
            <Button
              key={a}
              size="sm"
              variant={a === "complete" || a === "start" ? "primary" : "secondary"}
              loading={busy && action === a}
              onClick={() => {
                setError(null);
                setNote("");
                setAction(a);
                if (direct(a)) void run(a);
              }}
            >
              {t(`actions.${a}`)}
            </Button>
          ))}
        </div>
      ) : null}
      <Dialog
        open={action !== null && !direct(action)}
        onOpenChange={(o) => !o && setAction(null)}
        title={action ? `${t(`actions.${action}`)} — ${task.title}` : ""}
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setAction(null)}>
              {tc("cancel")}
            </Button>
            <Button onClick={() => action && run(action)} loading={busy} variant={action === "cancel" ? "danger" : "primary"}>
              {tc("confirm")}
            </Button>
          </>
        }
      >
        {action === "assign" ? (
          <Field id={`assign-${task.id}`} label={t("assignee")} error={error ?? undefined}>
            {(aria) => (
              <Select {...aria} value={assignee} onChange={(e) => setAssignee(e.target.value)}>
                <option value="">—</option>
                {(members ?? []).map((m) => (
                  <option key={m.membership_id} value={m.membership_id}>{m.name ?? m.membership_id}</option>
                ))}
              </Select>
            )}
          </Field>
        ) : (
          <Field
            id={`note-${task.id}`}
            label={action === "block" ? t("blockReason") : action === "cancel" ? t("cancelReason") : t("completeNote")}
            error={error ?? undefined}
          >
            {(aria) => <Textarea {...aria} value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} />}
          </Field>
        )}
      </Dialog>
    </li>
  );
}
