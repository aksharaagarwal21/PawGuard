// Copies MapLibre's module worker (and the shared chunk it imports) into public/ so the browser can load it
// from our own origin; bundlers cannot rewrite its relative import. Runs before dev and build.
import { copyFileSync, mkdirSync, realpathSync } from "node:fs";
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

// ZXing's QR reader (WebAssembly) for the certificate verifier's fallback scanner: served from our own origin so it
// works offline after the first visit (the library would otherwise fetch it from a CDN).
// pnpm keeps a package's own dependencies beside it: <store>/barcode-detector@x/node_modules/{barcode-detector,zxing-wasm}
const bd = realpathSync(path.resolve(import.meta.dirname, "../node_modules/barcode-detector"));
const zxing = path.join(bd, "..", "zxing-wasm");
const zout = path.resolve(import.meta.dirname, "../public/vendor/zxing");
mkdirSync(zout, { recursive: true });
copyFileSync(path.join(zxing, "dist/reader/zxing_reader.wasm"), path.join(zout, "zxing_reader.wasm"));
copyFileSync(path.join(zxing, "LICENSE"), path.join(zout, "LICENSE"));
console.log(`zxing reader copied to ${path.relative(process.cwd(), zout)}`);
