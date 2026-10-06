// Copies MapLibre's module worker (and the shared chunk it imports) into public/ so the browser can load it
// from our own origin; bundlers cannot rewrite its relative import. Runs before dev and build.
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const dist = path.dirname(require.resolve("maplibre-gl/dist/maplibre-gl.mjs"));
const out = path.resolve(import.meta.dirname, "../public/vendor/maplibre");
mkdirSync(out, { recursive: true });
for (const f of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs", "../LICENSE.txt"]) {
  copyFileSync(path.join(dist, f), path.join(out, path.basename(f)));
}
console.log(`maplibre worker copied to ${path.relative(process.cwd(), out)}`);
