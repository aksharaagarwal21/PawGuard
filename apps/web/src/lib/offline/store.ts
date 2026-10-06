"use client";

/**
 * Offline field kit storage (IndexedDB, this browser only). Holds the minimum needed to work through assigned
 * tasks without a connection: task essentials (no caregiver details, no exact locations, no photos), queued
 * changes, and which account/organisation they belong to. Everything expires and is wiped on sign-out or when the
 * person stops using the device for field work. This is not encrypted storage: see docs/THREAT_MODEL.md.
 */

const DB_NAME = "pawguard-field";
const DB_VERSION = 1;
export const CACHE_HOURS = 72;

export type CachedTask = {
  id: string;
  title: string;
  task_type: string;
  state: string;
  priority: string;
  instructions: string | null;
  area_id: string | null;
  area_name: string | null;
  animal_id: string | null;
  animal_reference: string | null;
  due_on: string | null;
  row_version: number;
};

export type OpStatus = "queued" | "conflict" | "rejected";

export type QueuedOp = {
  operation_id: string;
  operation_type: "task.transition" | "observation.create";
  actor_user_id: string;
  org_id: string;
  target_id?: string;
  base_row_version?: number;
  client_created_at: string;
  task?: { action: "start" | "complete" | "block"; note?: string | null };
  sighting?: { animal_id: string; observed_on: string; area_id?: string | null; notes?: string | null; field_task_id?: string | null };
  status: OpStatus;
  label: string;
  result_code?: string | null;
  message?: string | null;
  server_state?: string | null;
  server_row_version?: number | null;
};

export type FieldMeta = {
  device_id: string;
  user_id: string;
  org_id: string;
  org_name: string;
  cached_at: string;
  expires_at: string;
  last_sync_at?: string | null;
};

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains("meta")) db.createObjectStore("meta");
      if (!db.objectStoreNames.contains("tasks")) db.createObjectStore("tasks", { keyPath: "id" });
      if (!db.objectStoreNames.contains("queue")) db.createObjectStore("queue", { keyPath: "operation_id" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function run<T>(store: string, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T> | void): Promise<T | undefined> {
  const db = await open();
  try {
    return await new Promise<T | undefined>((resolve, reject) => {
      const tx = db.transaction(store, mode);
      const req = fn(tx.objectStore(store));
      tx.oncomplete = () => resolve(req ? req.result : undefined);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}

export async function getMeta(): Promise<FieldMeta | null> {
  const m = await run<FieldMeta>("meta", "readonly", (s) => s.get("meta"));
  return m ?? null;
}

export async function setMeta(meta: FieldMeta): Promise<void> {
  await run("meta", "readwrite", (s) => s.put(meta, "meta"));
}

export async function getTasks(): Promise<CachedTask[]> {
  return (await run<CachedTask[]>("tasks", "readonly", (s) => s.getAll())) ?? [];
}

export async function replaceTasks(tasks: CachedTask[]): Promise<void> {
  await run("tasks", "readwrite", (s) => {
    s.clear();
    for (const t of tasks) s.put(t);
  });
}

export async function putTask(task: CachedTask): Promise<void> {
  await run("tasks", "readwrite", (s) => s.put(task));
}

export async function getOps(): Promise<QueuedOp[]> {
  const ops = (await run<QueuedOp[]>("queue", "readonly", (s) => s.getAll())) ?? [];
  return ops.sort((a, b) => a.client_created_at.localeCompare(b.client_created_at));
}

export async function putOp(op: QueuedOp): Promise<void> {
  await run("queue", "readwrite", (s) => s.put(op));
}

export async function deleteOp(id: string): Promise<void> {
  await run("queue", "readwrite", (s) => s.delete(id));
}

/** Remove everything this app stored for offline work (IndexedDB, Cache Storage, service worker). */
export async function wipeOfflineData(): Promise<void> {
  await new Promise<void>((resolve) => {
    const req = indexedDB.deleteDatabase(DB_NAME);
    req.onsuccess = req.onerror = req.onblocked = () => resolve();
  });
  if ("serviceWorker" in navigator) {
    // Tell running workers to stop storing anything and clear their caches before unregistering: an
    // unregistered worker keeps controlling open pages until they close.
    for (const r of await navigator.serviceWorker.getRegistrations()) {
      const worker = r.active ?? r.waiting ?? r.installing;
      if (worker) {
        await new Promise<void>((resolve) => {
          const channel = new MessageChannel();
          const timer = setTimeout(resolve, 2000);
          channel.port1.onmessage = () => {
            clearTimeout(timer);
            resolve();
          };
          worker.postMessage({ type: "pawguard:wipe" }, [channel.port2]);
        });
      }
      await r.unregister();
    }
  }
  if ("caches" in window) {
    for (const k of await caches.keys()) if (k.startsWith("pawguard-")) await caches.delete(k);
  }
}

/** True when the kit exists but its cached data is past expiry (it is then wiped, keeping unsent changes). */
export async function expireIfStale(): Promise<boolean> {
  const meta = await getMeta();
  if (!meta || new Date(meta.expires_at) > new Date()) return false;
  await replaceTasks([]);
  return true;
}
