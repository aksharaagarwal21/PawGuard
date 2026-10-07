/**
 * QR reading for the verifier: the browser's BarcodeDetector where it supports QR codes, otherwise the
 * `barcode-detector` ponyfill (ZXing compiled to WebAssembly), loaded on demand from our own origin so it also works
 * offline after the first visit.
 */
type Detector = { detect: (source: ImageBitmapSource) => Promise<{ rawValue: string }[]> };

let cached: Promise<Detector> | null = null;

export function getDetector(): Promise<Detector> {
  cached ??= (async () => {
    const Native = (globalThis as { BarcodeDetector?: { new (o: { formats: string[] }): Detector; getSupportedFormats?: () => Promise<string[]> } }).BarcodeDetector;
    if (Native?.getSupportedFormats) {
      try {
        if ((await Native.getSupportedFormats()).includes("qr_code")) return new Native({ formats: ["qr_code"] });
      } catch {
        /* fall through to the WebAssembly reader */
      }
    }
    const mod = await import("barcode-detector/ponyfill");
    mod.prepareZXingModule({
      overrides: {
        locateFile: (path: string, prefix: string) => (path.endsWith(".wasm") ? "/vendor/zxing/zxing_reader.wasm" : prefix + path),
      },
    });
    return new mod.BarcodeDetector({ formats: ["qr_code"] }) as unknown as Detector;
  })();
  return cached;
}

/** First QR text found in an image (photo upload), or null. */
export async function readImage(file: Blob): Promise<string | null> {
  const bitmap = await createImageBitmap(file);
  try {
    const found = await (await getDetector()).detect(bitmap);
    return found[0]?.rawValue ?? null;
  } finally {
    bitmap.close();
  }
}

/** Store the verify page and everything it loaded in the field-kit cache so it opens offline (service worker). */
export async function prepareOffline(): Promise<void> {
  if (!("serviceWorker" in navigator) || !("caches" in window)) return;
  await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  const cache = await caches.open("pawguard-shell-v1");
  const urls = new Set<string>([window.location.pathname, "/vendor/zxing/zxing_reader.wasm"]);
  for (const e of performance.getEntriesByType("resource")) {
    const u = new URL(e.name);
    if (u.origin === window.location.origin && u.pathname.startsWith("/_next/static/")) urls.add(u.pathname + u.search);
  }
  await Promise.all(
    [...urls].map(async (u) => {
      if (u !== window.location.pathname && (await cache.match(u))) return;
      await cache.add(u).catch(() => undefined);
    }),
  );
}
