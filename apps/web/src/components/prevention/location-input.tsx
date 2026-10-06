"use client";

import { LocateFixed } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

export type CapturedLocation = { lat: number; lon: number; accuracy_m: number; method: "gps" };

/**
 * Asks for the device location only when the person presses the button (never on page load) and never keeps
 * watching. Denial is a normal outcome: the form continues with an area choice instead.
 */
export function LocationInput({
  value,
  onChange,
}: {
  value: CapturedLocation | null;
  onChange: (loc: CapturedLocation | null) => void;
}) {
  const t = useTranslations("animalForm");
  const [status, setStatus] = useState<"idle" | "locating" | "denied" | "unavailable">("idle");

  function locate() {
    if (!("geolocation" in navigator)) return setStatus("unavailable");
    setStatus("locating");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setStatus("idle");
        onChange({
          lat: Number(pos.coords.latitude.toFixed(6)),
          lon: Number(pos.coords.longitude.toFixed(6)),
          accuracy_m: Math.round(pos.coords.accuracy),
          method: "gps",
        });
      },
      (err) => setStatus(err.code === err.PERMISSION_DENIED ? "denied" : "unavailable"),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
    );
  }

  return (
    <div className="space-y-2" aria-live="polite">
      {value ? (
        <div className="flex flex-wrap items-center gap-3 rounded-control bg-sage p-3 text-sm">
          <span>{t("locationCaptured", { accuracy: value.accuracy_m })}</span>
          <button type="button" onClick={() => onChange(null)} className="min-h-11 font-semibold text-primary underline">
            {t("removeLocation")}
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={locate}
          disabled={status === "locating"}
          className="inline-flex min-h-11 items-center gap-2 rounded-control border border-control bg-surface px-4 font-display text-sm font-semibold hover:bg-sage disabled:opacity-60"
        >
          <LocateFixed aria-hidden className="size-4" />
          {t("useLocation")}
        </button>
      )}
      {status === "denied" ? <p className="text-sm text-ink-2">{t("locationDenied")}</p> : null}
      {status === "unavailable" ? <p className="text-sm text-ink-2">{t("locationUnavailable")}</p> : null}
    </div>
  );
}
