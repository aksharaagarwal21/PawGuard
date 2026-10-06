"use client";

import { browserApi } from "@/lib/api-browser";

import {
  CACHE_HOURS,
  deleteOp,
  getMeta,
  getOps,
  getTasks,
  putOp,
  putTask,
  replaceTasks,
  setMeta,
  type CachedTask,
  type FieldMeta,
  type QueuedOp,
} from "./store";

export const SHELL_CACHE = "pawguard-shell-v1";
const OPEN_STATES = ["assigned", "in_progress", "blocked"] as const;

export type SyncSummary = { accepted: number; conflicts: number; rejected: number; error?: "offline" | "signedOut" | "accessEnded" | "failed" };

/** Download today's assigned tasks for this account/organisation and make the field kit available offline. */
export async function prepareKit(fieldPath: string): Promise<{ ok: true; meta: FieldMeta; tasks: number } | { ok: false; reason: string }> {
  const org = await browserApi.GET("/api/v1/me/organisation");
  if (!org.data) return { ok: false, reason: org.response?.status === 401 ? "signedOut" : "failed" };
  const previous = await getMeta();
  if (previous && (previous.user_id !== org.data.user_id || previous.org_id !== org.data.org_id)) {
    const pending = (await getOps()).length;
    if (pending) return { ok: false, reason: "otherAccountPending" };
  }
  const tasks = await browserApi.GET("/api/v1/tasks", { params: { query: { mine: true, state: [...OPEN_STATES], limit: 100 } } });
  if (!tasks.data) return { ok: false, reason: "failed" };
  const now = new Date();
  const meta: FieldMeta = {
    device_id: previous?.device_id ?? `dev-${crypto.randomUUID()}`,
    user_id: org.data.user_id,
    org_id: org.data.org_id,
    org_name: org.data.org_name,
    cached_at: now.toISOString(),
    expires_at: new Date(now.getTime() + CACHE_HOURS * 3600_000).toISOString(),
    last_sync_at: previous?.last_sync_at ?? null,
  };
  await replaceTasks(
    tasks.data.items.map<CachedTask>((t) => ({
      id: t.id,
      title: t.title,
      task_type: t.task_type,
      state: t.state,
      priority: t.priority,
      instructions: t.instructions,
      area_id: t.area?.id ?? null,
      area_name: t.area?.name ?? null,
      animal_id: t.animal_id,
      animal_reference: t.animal_reference,
      due_on: t.due_on,
      row_version: t.row_version,
    })),
  );
  await setMeta(meta);
  await installShell(fieldPath);
  return { ok: true, meta, tasks: tasks.data.items.length };
}

/** Register the service worker and store the field kit page and its static assets for offline use. */
async function installShell(fieldPath: string): Promise<void> {
  if (!("serviceWorker" in navigator) || !("caches" in window)) return;
  await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  await navigator.serviceWorker.ready;
  const assets = performance
    .getEntriesByType("resource")
    .map((e) => e.name)
    .filter((u) => {
      const p = new URL(u, location.href);
      return p.origin === location.origin && p.pathname.startsWith("/_next/static/");
    });
  const cache = await caches.open(SHELL_CACHE);
  await cache.addAll([fieldPath, ...new Set(assets)]);
}

/** Queue a change made on this device and reflect it locally until the server answers. */
export async function queueChange(op: Omit<QueuedOp, "operation_id" | "client_created_at" | "status">, localTask?: CachedTask): Promise<void> {
  await putOp({ ...op, operation_id: crypto.randomUUID(), client_created_at: new Date().toISOString(), status: "queued" });
  if (localTask) await putTask(localTask);
}

/** Send queued changes for the signed-in account and selected organisation; keep anything not applied. */
export async function sendQueued(): Promise<SyncSummary> {
  const meta = await getMeta();
  const summary: SyncSummary = { accepted: 0, conflicts: 0, rejected: 0 };
  if (!meta) return summary;
  const ops = (await getOps()).filter((o) => o.status === "queued" && o.org_id === meta.org_id && o.actor_user_id === meta.user_id);
  if (!ops.length) return summary;
  let res;
  try {
    res = await browserApi.POST("/api/v1/sync/operations", {
      body: {
        device_id: meta.device_id,
        operations: ops.map((o) => ({
          operation_id: o.operation_id,
          operation_type: o.operation_type,
          actor_user_id: o.actor_user_id,
          org_id: o.org_id,
          target_id: o.target_id ?? null,
          base_row_version: o.base_row_version ?? null,
          client_created_at: o.client_created_at,
          task: o.task ?? null,
          sighting: o.sighting ?? null,
        })),
      },
    });
  } catch {
    return { ...summary, error: "offline" };
  }
  if (!res.data) {
    const status = res.response?.status;
    return { ...summary, error: status === 401 ? "signedOut" : status === 403 ? "accessEnded" : "failed" };
  }
  const tasks = new Map((await getTasks()).map((t) => [t.id, t]));
  for (const r of res.data.results) {
    const op = ops.find((o) => o.operation_id === r.operation_id);
    if (!op) continue;
    if (r.state === "accepted") {
      summary.accepted += 1;
      await deleteOp(op.operation_id);
      const t = op.target_id ? tasks.get(op.target_id) : undefined;
      if (t && r.server_row_version) await putTask({ ...t, row_version: r.server_row_version });
    } else {
      if (r.state === "conflict") summary.conflicts += 1;
      else summary.rejected += 1;
      await putOp({ ...op, status: r.state, result_code: r.result_code, message: r.message, server_state: r.server_state, server_row_version: r.server_row_version });
      const t = op.target_id ? tasks.get(op.target_id) : undefined;
      if (t && r.server_state && r.server_row_version) await putTask({ ...t, state: r.server_state, row_version: r.server_row_version });
    }
  }
  await setMeta({ ...meta, last_sync_at: new Date().toISOString() });
  return summary;
}

/** The person chose to drop a change the server did not apply; recorded on the server for the audit trail. */
export async function discardChange(op: QueuedOp, resolution: "discarded" | "superseded" = "discarded"): Promise<void> {
  if (op.status !== "queued") {
    try {
      await browserApi.POST("/api/v1/sync/operations/{operation_id}/resolve", {
        params: { path: { operation_id: op.operation_id } },
        body: { resolution },
      });
    } catch {
      // Offline: the local copy is dropped; the server already holds the conflict record.
    }
  }
  await deleteOp(op.operation_id);
}
