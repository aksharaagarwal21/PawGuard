"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import type { FeatureCollection } from "geojson";
import { LngLatBounds, Map as MapLibreMap, NavigationControl, setWorkerUrl, type StyleSpecification } from "maplibre-gl";
import { useEffect, useRef } from "react";

type FC = FeatureCollection;

// Served from our origin (copied by scripts/copy-maplibre-worker.mjs); satisfies worker-src 'self'.
setWorkerUrl("/vendor/maplibre/maplibre-gl-worker.mjs");

/**
 * Operational map. Areas are outlines, sightings filled circles, open tasks rings (shape + colour, with a text
 * legend outside the map). Without a configured tile provider the map draws on a plain background — tiles are
 * never fetched from a provider whose terms have not been configured.
 */
export default function AreaMap({
  areas,
  sightings,
  tasks,
  tileUrl,
  attribution,
  label,
}: {
  areas: FC;
  sightings: FC;
  tasks: FC;
  tileUrl?: string;
  attribution?: string;
  label: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const style: StyleSpecification = {
      version: 8,
      sources: tileUrl
        ? { base: { type: "raster", tiles: [tileUrl], tileSize: 256, attribution: attribution ?? "", maxzoom: 19 } }
        : {},
      layers: [
        { id: "bg", type: "background", paint: { "background-color": "#F7F8F3" } },
        ...(tileUrl ? [{ id: "base", type: "raster" as const, source: "base", paint: { "raster-saturation": -0.4 } }] : []),
      ],
    };
    const map = new MapLibreMap({ container: ref.current, style, center: [80.25, 13.05], zoom: 12, attributionControl: { compact: true } });
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      map.addSource("areas", { type: "geojson", data: areas });
      map.addLayer({ id: "areas-fill", type: "fill", source: "areas", paint: { "fill-color": "#205C4F", "fill-opacity": 0.06 } });
      map.addLayer({ id: "areas-line", type: "line", source: "areas", paint: { "line-color": "#205C4F", "line-width": 2 } });
      map.addSource("sightings", { type: "geojson", data: sightings });
      map.addLayer({
        id: "sightings",
        type: "circle",
        source: "sightings",
        paint: { "circle-radius": 5, "circle-color": "#205C4F", "circle-stroke-color": "#FFFFFF", "circle-stroke-width": 1.5 },
      });
      map.addSource("tasks", { type: "geojson", data: tasks });
      map.addLayer({
        id: "tasks",
        type: "circle",
        source: "tasks",
        paint: { "circle-radius": 9, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#A43E35", "circle-stroke-width": 3 },
      });
      const bounds = new LngLatBounds();
      const add = (fc: FC) =>
        fc.features.forEach((f) => {
          const g = f.geometry;
          if (g.type === "Point") bounds.extend(g.coordinates as [number, number]);
          if (g.type === "MultiPolygon") g.coordinates.flat(2).forEach((c: number[]) => bounds.extend(c as [number, number]));
          if (g.type === "Polygon") g.coordinates.flat(1).forEach((c: number[]) => bounds.extend(c as [number, number]));
        });
      add(areas);
      add(sightings);
      if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 32, maxZoom: 15, duration: 0 });
    });
    return () => map.remove();
  }, [areas, sightings, tasks, tileUrl, attribution]);
  return <div ref={ref} role="region" aria-label={label} className="h-[22rem] w-full overflow-hidden rounded-card border border-divider md:h-[30rem]" />;
}
