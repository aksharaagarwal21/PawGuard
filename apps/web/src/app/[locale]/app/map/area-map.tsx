"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import type { FeatureCollection } from "geojson";
import { LngLatBounds, Map as MapLibreMap, NavigationControl, Popup, setWorkerUrl, type StyleSpecification } from "maplibre-gl";
import { useEffect, useRef } from "react";

type FC = FeatureCollection;

/** Vaccination status colours (also explained in the legend and in each point's details). */
export const STATUS_COLOURS: Record<string, string> = {
  up_to_date: "#205C4F",
  verified: "#205C4F",
  due_soon: "#B7791F",
  overdue: "#A43E35",
  no_verified_record: "#6B7280",
};

export type MapLabels = Record<string, string>;

/** Popup body built from text nodes only (names and titles are typed by people — never inserted as HTML). */
function popupBody(lines: (string | null | undefined)[], link?: { href: string; text: string }): HTMLElement {
  const box = document.createElement("div");
  box.style.cssText = "font: 14px/1.4 system-ui, sans-serif; color: #1f2a26; max-width: 240px";
  lines.filter(Boolean).forEach((line, i) => {
    const p = document.createElement("p");
    p.textContent = line ?? "";
    if (i === 0) p.style.fontWeight = "600";
    box.appendChild(p);
  });
  if (link) {
    const a = document.createElement("a");
    a.href = link.href;
    a.textContent = link.text;
    a.style.cssText = "display:inline-block;margin-top:4px;font-weight:600;color:#205C4F";
    box.appendChild(a);
  }
  return box;
}

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
  labels,
  locale,
}: {
  areas: FC;
  sightings: FC;
  tasks: FC;
  tileUrl?: string;
  attribution?: string;
  label: string;
  labels: MapLabels;
  locale: string;
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
        paint: {
          "circle-radius": 7,
          "circle-color": ["match", ["get", "status"], ...Object.entries(STATUS_COLOURS).flat(), "#205C4F"] as never,
          "circle-stroke-color": "#FFFFFF",
          "circle-stroke-width": 2,
        },
      });
      map.addSource("tasks", { type: "geojson", data: tasks });
      map.addLayer({
        id: "tasks",
        type: "circle",
        source: "tasks",
        paint: { "circle-radius": 9, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#A43E35", "circle-stroke-width": 3 },
      });
      const fmt = (d: unknown) =>
        typeof d === "string" && d
          ? new Date(d + "T00:00:00").toLocaleDateString(locale === "en" ? "en-IN" : locale + "-IN", { day: "numeric", month: "short", year: "numeric" })
          : null;
      const open = (lngLat: { lng: number; lat: number }, body: HTMLElement) =>
        new Popup({ closeButton: true, maxWidth: "260px" }).setLngLat(lngLat).setDOMContent(body).addTo(map);
      map.on("click", "sightings", (e) => {
        const p = (e.features?.[0]?.properties ?? {}) as Record<string, string | null>;
        const who = [p.name, p.species ? (labels["species_" + p.species] ?? p.species) : null].filter(Boolean).join(" · ");
        open(
          e.lngLat,
          popupBody(
            [
              who || p.reference,
              p.reference,
              labels["status_" + (p.status ?? "no_verified_record")],
              p.last_verified ? labels.lastVerified + " " + fmt(p.last_verified) : null,
              p.next_due ? labels.nextDue + " " + fmt(p.next_due) : null,
              p.day ? labels.seen + " " + fmt(p.day) : null,
            ],
            p.animal_id ? { href: "/" + locale + "/app/animals/" + p.animal_id, text: labels.openRecord ?? "Open" } : undefined,
          ),
        );
      });
      map.on("click", "tasks", (e) => {
        const p = (e.features?.[0]?.properties ?? {}) as Record<string, string | null>;
        open(e.lngLat, popupBody([p.title, labels["task_" + p.state] ?? p.state], { href: "/" + locale + "/app/tasks", text: labels.openTasks ?? "Tasks" }));
      });
      map.on("click", "areas-fill", (e) => {
        if (map.queryRenderedFeatures(e.point, { layers: ["sightings", "tasks"] }).length) return;
        const p = (e.features?.[0]?.properties ?? {}) as Record<string, string | null>;
        open(e.lngLat, popupBody([p.name, p.code]));
      });
      for (const layer of ["sightings", "tasks", "areas-fill"]) {
        map.on("mouseenter", layer, () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", layer, () => {
          map.getCanvas().style.cursor = "";
        });
      }
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
  }, [areas, sightings, tasks, tileUrl, attribution, labels, locale]);
  return <div ref={ref} role="region" aria-label={label} className="h-[22rem] w-full overflow-hidden rounded-card border border-divider md:h-[30rem]" />;
}
