"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Button } from "@pawguard/ui";

import { browserApi } from "@/lib/api-browser";

type State = "loading" | "unsupported" | "ios-install" | "denied" | "off" | "on";

function urlBase64ToBytes(value: string): Uint8Array<ArrayBuffer> {
  const pad = "=".repeat((4 - (value.length % 4)) % 4);
  const raw = atob((value + pad).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

async function pushRegistration(): Promise<ServiceWorkerRegistration> {
  const existing = await navigator.serviceWorker.getRegistration("/push/");
  return existing ?? navigator.serviceWorker.register("/push-sw.js", { scope: "/push/" });
}

/** Wait until *this* registration's worker is active. (`navigator.serviceWorker.ready` waits for a worker that
 *  controls the current page — the push worker's scope is /push/, so on this page it would never resolve.) */
async function activated(reg: ServiceWorkerRegistration, ms = 15_000): Promise<ServiceWorkerRegistration> {
  if (reg.active) return reg;
  const worker = reg.installing ?? reg.waiting;
  await new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error("service worker did not start")), ms);
    worker?.addEventListener("statechange", () => {
      if (worker.state === "activated") {
        window.clearTimeout(timer);
        resolve();
      }
    });
    if (!worker) {
      window.clearTimeout(timer);
      resolve();
    }
  });
  return reg;
}

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return Promise.race([p, new Promise<T>((_, reject) => window.setTimeout(() => reject(new Error("timeout")), ms))]);
}

const isBrave = () => Boolean((navigator as Navigator & { brave?: unknown }).brave);

/** Turn browser notifications on or off for this device. Explains iPhone's Home Screen requirement. */
export function PushToggle({ vapidKey, devices, onChanged }: { vapidKey: string | null; devices: number; onChanged: () => void }) {
  const t = useTranslations("notify.push");
  const [state, setState] = useState<State>("loading");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isBraveBrowser, setIsBraveBrowser] = useState(false);

  useEffect(() => {
    const raf = requestAnimationFrame(async () => {
      setIsBraveBrowser(isBrave());
      const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
      const standalone = window.matchMedia("(display-mode: standalone)").matches;
      if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
        return setState(ios && !standalone ? "ios-install" : "unsupported");
      }
      if (Notification.permission === "denied") return setState("denied");
      try {
        const reg = await navigator.serviceWorker.getRegistration("/push/");
        const sub = await reg?.pushManager.getSubscription();
        setState(sub ? "on" : "off");
      } catch {
        setState("off");
      }
    });
    return () => cancelAnimationFrame(raf);
  }, []);

  async function turnOn() {
    if (!vapidKey) return;
    setBusy(true);
    setError(null);
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setState(permission === "denied" ? "denied" : "off");
        return;
      }
      const reg = await activated(await pushRegistration());
      const sub = await withTimeout(
        reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToBytes(vapidKey) }),
        20_000,
      );
      const json = sub.toJSON();
      const { error: apiError } = await browserApi.POST("/api/v1/my/push-subscriptions", {
        body: {
          endpoint: json.endpoint ?? "",
          keys: { p256dh: json.keys?.p256dh ?? "", auth: json.keys?.auth ?? "" },
          user_agent: navigator.userAgent.slice(0, 300),
        },
      });
      if (apiError) {
        await sub.unsubscribe();
        setError(t("failed"));
        return;
      }
      setState("on");
      onChanged();
    } catch {
      // Brave blocks the browser push service unless the person switches it on in Brave's settings.
      setError(isBrave() ? t("brave") : t("failed"));
    } finally {
      setBusy(false);
    }
  }

  async function turnOff() {
    setBusy(true);
    try {
      const reg = await navigator.serviceWorker.getRegistration("/push/");
      const sub = await reg?.pushManager.getSubscription();
      if (sub) {
        await browserApi.POST("/api/v1/my/push-subscriptions/remove", { body: { endpoint: sub.endpoint } });
        await sub.unsubscribe();
      }
      setState("off");
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2 text-sm">
      <p className="text-ink-2">{t("devices", { count: devices })}</p>
      {state === "on" ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold">{t("onHere")}</span>
          <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={turnOff}>
            {t("turnOff")}
          </Button>
        </div>
      ) : state === "off" ? (
        <>
          <Button type="button" size="sm" disabled={busy || !vapidKey} onClick={turnOn}>
            {busy ? t("turningOn") : t("turnOn")}
          </Button>
          {isBraveBrowser ? <p className="text-ink-2">{t("braveHint")}</p> : null}
        </>
      ) : state === "loading" ? null : (
        <p className="rounded-control bg-sand p-3">{t(`state.${state}`)}</p>
      )}
      {error ? <p className="font-semibold text-urgent">{error}</p> : null}
    </div>
  );
}
