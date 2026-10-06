"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

import { Button, Card, Dialog, EmptyState, Field, Notice, StatusChip, Textarea } from "@pawguard/ui";

import { uuid4 } from "@/lib/api-browser";
import { expireIfStale, getMeta, getOps, getTasks, putOp, wipeOfflineData, type CachedTask, type FieldMeta, type QueuedOp } from "@/lib/offline/store";
import { discardChange, prepareKit, queueChange, sendQueued, type SyncSummary } from "@/lib/offline/sync";

type Action = { kind: "complete" | "block" | "sighting"; task: CachedTask } | null;

const NEXT_STATE = { start: "in_progress", complete: "completed", block: "blocked" } as const;

async function loadState() {
  const expired = await expireIfStale();
  const [meta, tasks, ops] = await Promise.all([getMeta(), getTasks(), getOps()]);
  tasks.sort((a, b) => (a.due_on ?? "9999").localeCompare(b.due_on ?? "9999"));
  return { expired, meta, tasks, ops };
}

function subscribeOnline(cb: () => void): () => void {
  window.addEventListener("online", cb);
  window.addEventListener("offline", cb);
  return () => {
    window.removeEventListener("online", cb);
    window.removeEventListener("offline", cb);
  };
}

export function FieldKit({ locale }: { locale: string }) {
  const t = useTranslations("field");
  const tc = useTranslations("common");
  const [ready, setReady] = useState(false);
  const online = useSyncExternalStore(subscribeOnline, () => navigator.onLine, () => true);
  const [meta, setMeta] = useState<FieldMeta | null>(null);
  const [tasks, setTasks] = useState<CachedTask[]>([]);
  const [ops, setOps] = useState<QueuedOp[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "info" | "success" | "urgent" | "pending"; text: string } | null>(null);
  const [action, setAction] = useState<Action>(null);
  const [note, setNote] = useState("");
  const [confirmStop, setConfirmStop] = useState(false);
  const [expired, setExpired] = useState(false);

  const apply = useCallback((st: Awaited<ReturnType<typeof loadState>>) => {
    setExpired(st.expired);
    setMeta(st.meta);
    setTasks(st.tasks);
    setOps(st.ops);
    setReady(true);
  }, []);
  const reload = useCallback(async () => apply(await loadState()), [apply]);

  const report = useCallback(
    (s: SyncSummary) => {
      if (s.error === "offline") setMessage({ tone: "pending", text: t("stillOffline") });
      else if (s.error === "signedOut") setMessage({ tone: "urgent", text: t("signInToSend") });
      else if (s.error === "accessEnded") setMessage({ tone: "urgent", text: t("accessEnded") });
      else if (s.error) setMessage({ tone: "urgent", text: t("sendFailed") });
      else if (s.accepted || s.conflicts || s.rejected)
        setMessage({ tone: s.conflicts || s.rejected ? "pending" : "success", text: t("sentSummary", { accepted: s.accepted, conflicts: s.conflicts, rejected: s.rejected }) });
    },
    [t],
  );

  const send = useCallback(async () => {
    setBusy(true);
    report(await sendQueued());
    setBusy(false);
    await reload();
  }, [reload, report]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const st = await loadState();
      if (!cancelled) apply(st);
    })();
    const on = () => void send(); // reconnected: send what was saved on this device
    window.addEventListener("online", on);
    return () => {
      cancelled = true;
      window.removeEventListener("online", on);
    };
  }, [apply, send]);

  async function enable() {
    setBusy(true);
    setMessage(null);
    const r = await prepareKit(`/${locale}/field`);
    setBusy(false);
    if (r.ok) setMessage({ tone: "success", text: t("prepared", { n: r.tasks }) });
    else setMessage({ tone: "urgent", text: t(`prepareError.${r.reason}` as "prepareError.failed") });
    await reload();
  }

  async function stop() {
    await wipeOfflineData();
    setConfirmStop(false);
    setMessage({ tone: "info", text: t("stopped") });
    await reload();
  }

  async function act(task: CachedTask, kind: "start" | "complete" | "block", text?: string) {
    if (!meta) return;
    await queueChange(
      {
        operation_type: "task.transition",
        actor_user_id: meta.user_id,
        org_id: meta.org_id,
        target_id: task.id,
        base_row_version: task.row_version,
        task: { action: kind, note: text || null },
        label: t(`label.${kind}`, { title: task.title }),
      },
      { ...task, state: NEXT_STATE[kind] },
    );
    await reload();
    if (navigator.onLine) await send();
  }

  async function sighting(task: CachedTask, text: string) {
    if (!meta || !task.animal_id) return;
    await queueChange({
      operation_type: "observation.create",
      actor_user_id: meta.user_id,
      org_id: meta.org_id,
      sighting: { animal_id: task.animal_id, observed_on: new Date().toISOString().slice(0, 10), area_id: task.area_id, notes: text || null, field_task_id: task.id },
      label: t("label.sighting", { ref: task.animal_reference ?? "" }),
    });
    await reload();
    if (navigator.onLine) await send();
  }

  async function submitAction() {
    if (!action) return;
    if (action.kind === "block" && note.trim().length < 3) return;
    if (action.kind === "sighting") await sighting(action.task, note.trim());
    else await act(action.task, action.kind, note.trim());
    setAction(null);
    setNote("");
  }

  async function retryOnLatest(op: QueuedOp) {
    if (!op.server_row_version) return;
    await putOp({ ...op, operation_id: uuid4(), base_row_version: op.server_row_version, status: "queued", result_code: null, message: null, client_created_at: new Date().toISOString() });
    await discardChange(op, "superseded");
    await reload();
    if (navigator.onLine) await send();
  }

  const pendingFor = (taskId: string) => ops.some((o) => o.status === "queued" && (o.target_id === taskId || o.sighting?.field_task_id === taskId));
  const problems = ops.filter((o) => o.status !== "queued");
  const queued = ops.filter((o) => o.status === "queued");

  if (!ready) return <p className="container-pg py-6">{t("loading")}</p>;

  return (
    <main id="main" className="container-pg max-w-3xl space-y-5 py-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl">{t("title")}</h1>
          {meta ? <p className="text-ink-2">{t("forOrg", { org: meta.org_name })}</p> : null}
        </div>
        <StatusChip kind={online ? "verified" : "neutral"}>{online ? t("online") : t("offline")}</StatusChip>
      </header>
      {message ? (
        <Notice tone={message.tone} title={message.text} live="polite" />
      ) : null}
      {expired ? <Notice tone="pending" title={t("expiredTitle")}><p>{t("expiredBody")}</p></Notice> : null}

      {!meta ? (
        <Card className="space-y-3">
          <h2 className="text-lg">{t("setupTitle")}</h2>
          <p>{t("setupBody")}</p>
          <ul className="list-disc space-y-1 pl-5 text-ink-2">
            <li>{t("setupStores")}</li>
            <li>{t("setupRisk")}</li>
            <li>{t("setupNotStored")}</li>
          </ul>
          <Button onClick={enable} loading={busy} disabled={!online}>
            {t("enable")}
          </Button>
          {!online ? <p className="text-sm text-ink-2">{t("needsConnection")}</p> : null}
        </Card>
      ) : (
        <Card className="space-y-3">
          <p className="text-sm text-ink-2">{t("savedUntil", { date: new Date(meta.expires_at).toLocaleString(locale) })}</p>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={enable} loading={busy} disabled={!online || queued.length > 0}>
              {t("refresh")}
            </Button>
            <Button onClick={send} loading={busy} disabled={!online || queued.length === 0}>
              {t("sendNow", { n: queued.length })}
            </Button>
            <Button variant="quiet" onClick={() => setConfirmStop(true)}>
              {t("stop")}
            </Button>
          </div>
          {queued.length > 0 && !online ? <p role="status">{t("waitingToSend", { n: queued.length })}</p> : null}
        </Card>
      )}

      {problems.length ? (
        <section aria-labelledby="problems" className="space-y-2">
          <h2 id="problems" className="text-lg">{t("needsDecision")}</h2>
          {problems.map((o) => (
            <Card key={o.operation_id} className="space-y-2">
              <p className="font-semibold">{o.label}</p>
              {o.status === "conflict" ? (
                <p>{t("conflictBody", { state: o.server_state ? t(`state.${o.server_state}` as "state.assigned") : "?" })}</p>
              ) : (
                <p>{t("rejectedBody", { reason: o.message ?? o.result_code ?? "" })}</p>
              )}
              <div className="flex flex-wrap gap-2">
                {o.status === "conflict" && o.operation_type === "task.transition" && o.server_state && ["assigned", "in_progress", "blocked"].includes(o.server_state) ? (
                  <Button onClick={() => retryOnLatest(o)} disabled={!online}>
                    {t("applyToLatest")}
                  </Button>
                ) : null}
                <Button variant="secondary" onClick={async () => { await discardChange(o); await reload(); }}>
                  {t("discard")}
                </Button>
              </div>
            </Card>
          ))}
        </section>
      ) : null}

      {meta ? (
        <section aria-labelledby="tasks" className="space-y-2">
          <h2 id="tasks" className="text-lg">{t("tasksTitle")}</h2>
          {tasks.length === 0 ? (
            <EmptyState title={t("noTasks")} />
          ) : (
            <ul className="space-y-3">
              {tasks.map((task) => (
                <li key={task.id}>
                  <Card className="space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-display font-semibold">{task.title}</p>
                      <span className="flex gap-2">
                        {pendingFor(task.id) ? <StatusChip kind="submitted">{t("notSent")}</StatusChip> : null}
                        <StatusChip kind={task.state === "completed" ? "verified" : "neutral"}>{t(`state.${task.state}` as "state.assigned")}</StatusChip>
                      </span>
                    </div>
                    <p className="text-sm text-ink-2">
                      {[task.area_name, task.animal_reference, task.due_on ? t("due", { date: task.due_on }) : null].filter(Boolean).join(" · ")}
                    </p>
                    {task.instructions ? <p className="text-sm">{task.instructions}</p> : null}
                    <div className="flex flex-wrap gap-2">
                      {["assigned", "blocked"].includes(task.state) ? (
                        <Button size="sm" onClick={() => act(task, "start")}>
                          {t("start")}
                        </Button>
                      ) : null}
                      {["assigned", "in_progress"].includes(task.state) ? (
                        <>
                          <Button size="sm" onClick={() => setAction({ kind: "complete", task })}>
                            {t("complete")}
                          </Button>
                          <Button size="sm" variant="secondary" onClick={() => setAction({ kind: "block", task })}>
                            {t("block")}
                          </Button>
                        </>
                      ) : null}
                      {task.animal_id && !["completed", "cancelled"].includes(task.state) ? (
                        <Button size="sm" variant="secondary" onClick={() => setAction({ kind: "sighting", task })}>
                          {t("recordSighting")}
                        </Button>
                      ) : null}
                    </div>
                  </Card>
                </li>
              ))}
            </ul>
          )}
          <p className="text-sm text-ink-2">{t("notOffline")}</p>
        </section>
      ) : null}

      <p>
        <a href={`/${locale}/app`}>{t("openApp")}</a>
      </p>

      <Dialog
        open={action !== null}
        onOpenChange={(o) => !o && setAction(null)}
        title={action ? t(`dialog.${action.kind}`, { title: action.task.title, ref: action.task.animal_reference ?? "" }) : ""}
        description={action?.kind === "sighting" ? t("sightingExplain") : undefined}
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setAction(null)}>
              {tc("cancel")}
            </Button>
            <Button onClick={submitAction} disabled={action?.kind === "block" && note.trim().length < 3}>
              {t("saveOnDevice")}
            </Button>
          </>
        }
      >
        <Field id="field-note" label={action?.kind === "block" ? t("blockReason") : t("note")} marker={action?.kind === "block" ? undefined : tc("optional")}>
          {(aria) => <Textarea {...aria} value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} />}
        </Field>
      </Dialog>
      <Dialog
        open={confirmStop}
        onOpenChange={setConfirmStop}
        title={t("stopTitle")}
        description={queued.length || problems.length ? t("stopWithPending", { n: queued.length + problems.length }) : t("stopBody")}
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmStop(false)}>
              {tc("cancel")}
            </Button>
            <Button variant="danger" onClick={stop}>
              {t("stopConfirm")}
            </Button>
          </>
        }
      />
    </main>
  );
}

