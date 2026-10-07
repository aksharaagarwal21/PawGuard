/*
 * PawGuard service worker — registered after a person chooses "use this device for field work", or when the public
 * certificate verifier (/verify) is opened. It stores those two pages (neither contains personal data), the QR reader's
 * WebAssembly file and content-hashed static assets, so they open without a connection. It never stores API
 * responses, sign-in traffic, photos or other pages' HTML.
 */
const SHELL = "pawguard-shell-v1";
const FIELD = /^\/(en|ta|hi)\/field\/?$/;
const VERIFY = /^\/(en|ta|hi)\/verify\/?$/;
let disabled = false; // set when the person signs out or stops offline use; this worker then stores nothing

async function wipe() {
  disabled = true;
  for (const key of await caches.keys()) if (key.startsWith("pawguard-")) await caches.delete(key);
}

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "pawguard:wipe") {
    event.waitUntil(wipe().then(() => event.ports[0] && event.ports[0].postMessage("wiped")));
  }
});

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      for (const key of await caches.keys()) if (key.startsWith("pawguard-") && key !== SHELL) await caches.delete(key);
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (disabled || req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth")) return; // never cached

  if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/vendor/zxing/")) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(SHELL);
        const hit = await cache.match(req);
        if (hit) return hit;
        const res = await fetch(req);
        if (res.ok) cache.put(req, res.clone());
        return res;
      })(),
    );
    return;
  }

  if (req.mode === "navigate") {
    event.respondWith(
      (async () => {
        try {
          const res = await fetch(req);
          if ((FIELD.test(url.pathname) || VERIFY.test(url.pathname)) && res.ok) {
            (await caches.open(SHELL)).put(url.pathname, res.clone());
          }
          return res;
        } catch (err) {
          const cache = await caches.open(SHELL);
          const locale = (url.pathname.match(/^\/(en|ta|hi)\//) || [])[1] || "en";
          const fallback = (await cache.match(url.pathname)) || (await cache.match(`/${locale}/field`)) || (await cache.match("/en/field"));
          if (fallback) return fallback; // offline: the field kit is the only page that works without a connection
          throw err;
        }
      })(),
    );
  }
});
