import fs from "node:fs";

import { test } from "@playwright/test";

/**
 * First-load measurements against the running production build (`next start`) on this machine, no network
 * throttling. Results are written to docs/evidence/ for IMPLEMENTATION_STATUS. These are observations, not
 * targets met under field conditions.
 */
test.describe("first-load measurements", () => {
  test.skip(({ isMobile }) => !isMobile, "measured once with the mobile profile");

  test("public pages", async ({ page }) => {
    const results: Record<string, unknown>[] = [];
    for (const path of ["/en", "/en/help", "/en/sign-in"]) {
      let bytes = 0;
      let requests = 0;
      const onResponse = async (r: import("@playwright/test").Response) => {
        requests += 1;
        const len = Number(r.headers()["content-length"] ?? 0);
        bytes += Number.isFinite(len) && len > 0 ? len : (await r.body().catch(() => Buffer.alloc(0))).length;
      };
      page.on("response", onResponse);
      await page.goto(path, { waitUntil: "load" });
      await page.waitForTimeout(1500);
      const m = await page.evaluate(
        () =>
          new Promise<Record<string, number>>((resolve) => {
            const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
            let lcp = 0;
            new PerformanceObserver((list) => {
              for (const e of list.getEntries()) lcp = Math.max(lcp, e.startTime);
            }).observe({ type: "largest-contentful-paint", buffered: true });
            let cls = 0;
            new PerformanceObserver((list) => {
              for (const e of list.getEntries() as unknown as { value: number; hadRecentInput: boolean }[]) {
                if (!e.hadRecentInput) cls += e.value;
              }
            }).observe({ type: "layout-shift", buffered: true });
            setTimeout(
              () =>
                resolve({
                  ttfb_ms: Math.round(nav.responseStart),
                  dom_content_loaded_ms: Math.round(nav.domContentLoadedEventEnd),
                  load_ms: Math.round(nav.loadEventEnd),
                  lcp_ms: Math.round(lcp),
                  cls: Number(cls.toFixed(4)),
                }),
              300,
            );
          }),
      );
      page.off("response", onResponse);
      results.push({ path, ...m, requests, transferred_kb: Math.round(bytes / 1024) });
    }
    fs.mkdirSync("../docs/evidence", { recursive: true });
    fs.writeFileSync(
      "../docs/evidence/phase2-first-load.json",
      JSON.stringify({ measured_at: new Date().toISOString(), profile: "Pixel 7 emulation, 360px, no throttling, local next start", results }, null, 2),
    );
    console.log(JSON.stringify(results, null, 2));
  });
});
