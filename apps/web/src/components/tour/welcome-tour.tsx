"use client";

import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { Button } from "@pawguard/ui";

export type TourStep = { target: string; key: string };
type Box = { top: number; left: number; width: number; height: number };

const memory = new Set<string>(); // fallback when browser storage is unavailable

function dismissed(id: string): boolean {
  if (memory.has(id)) return true;
  try {
    return window.localStorage.getItem(`pawguard.tour.${id}`) === "done";
  } catch {
    return false;
  }
}

function remember(id: string) {
  memory.add(id);
  try {
    window.localStorage.setItem(`pawguard.tour.${id}`, "done");
  } catch {
    // Private mode or blocked storage: the in-memory note still prevents a repeat in this session.
  }
}

/** First element matching the selector that is actually visible (e.g. the bell exists in two layouts). */
function findTarget(selector: string): HTMLElement | null {
  const all = Array.from(document.querySelectorAll<HTMLElement>(selector));
  return all.find((el) => el.getClientRects().length > 0 && el.offsetParent !== null) ?? all[0] ?? null;
}

/**
 * A short guided tour that highlights real elements. Starts on a role's first visit (not under automated browsers,
 * so test runs are not covered by it) or when the URL has ?tour=1 ("Show tour again"). Skippable; Back/Next/Done;
 * Escape skips, arrow keys move. Respects reduced motion (the global stylesheet removes transitions).
 */
export function WelcomeTour({ id, steps }: { id: string; steps: TourStep[] }) {
  const t = useTranslations("tour");
  const [open, setOpen] = useState(false);
  const [i, setI] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const forced = useSearchParams().get("tour") === "1";

  useEffect(() => {
    if (!(forced || (!navigator.webdriver && !dismissed(id)))) return;
    // Open after the first paint, once the highlighted elements have their final layout.
    const raf = requestAnimationFrame(() => {
      returnFocus.current = document.activeElement as HTMLElement | null;
      setI(0);
      setOpen(true);
    });
    return () => cancelAnimationFrame(raf);
  }, [id, forced]);

  const close = useCallback(() => {
    remember(id);
    setOpen(false);
    const url = new URL(window.location.href);
    if (url.searchParams.has("tour")) {
      url.searchParams.delete("tour");
      window.history.replaceState(null, "", url.toString());
    }
    returnFocus.current?.focus?.();
  }, [id]);

  const measure = useCallback(() => {
    const step = steps[i];
    const el = step ? findTarget(step.target) : null;
    if (!el) return setBox(null);
    const r = el.getBoundingClientRect();
    setBox({ top: r.top, left: r.left, width: r.width, height: r.height });
  }, [i, steps]);

  useLayoutEffect(() => {
    if (!open) return;
    const step = steps[i];
    const el = step ? findTarget(step.target) : null;
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
    const timer = window.setTimeout(measure, 250); // again after a smooth scroll settles
    const raf = requestAnimationFrame(measure);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.clearTimeout(timer);
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [open, i, steps, measure]);

  useEffect(() => {
    if (open) dialogRef.current?.focus();
  }, [open, i]);

  if (!open || steps.length === 0) return null;
  const step = steps[i]!;
  const last = i === steps.length - 1;
  const pad = 6;
  const vh = window.innerHeight;
  const wide = window.innerWidth >= 640;
  const below = !box || box.top + box.height + 220 < vh;
  const cardTop = box ? (below ? box.top + box.height + pad + 10 : Math.max(12, box.top - pad - 10)) : vh / 2;

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "Escape") close();
    else if (e.key === "ArrowRight" && !last) setI(i + 1);
    else if (e.key === "ArrowLeft" && i > 0) setI(i - 1);
  }

  return (
    <div className="fixed inset-0 z-50" aria-hidden={false}>
      {/* Dimmed page with a cut-out around the highlighted element. */}
      {box ? (
        <div
          aria-hidden
          className="pointer-events-none fixed rounded-card ring-2 ring-white motion-safe:transition-all motion-safe:duration-200 motion-safe:ease-calm"
          style={{
            top: box.top - pad,
            left: box.left - pad,
            width: box.width + pad * 2,
            height: box.height + pad * 2,
            boxShadow: "0 0 0 9999px rgb(32 58 52 / 0.55)",
          }}
        />
      ) : (
        <div aria-hidden className="fixed inset-0 bg-ink/55" />
      )}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
        aria-describedby="tour-body"
        tabIndex={-1}
        onKeyDown={onKey}
        className="fixed right-4 left-4 mx-auto max-w-sm rounded-card bg-surface p-5 shadow-card outline-none sm:right-auto"
        style={{
          top: below ? cardTop : undefined,
          bottom: below ? undefined : vh - cardTop,
          left: box && wide ? Math.min(Math.max(16, box.left), window.innerWidth - 400) : undefined,
        }}
      >
        <p className="text-xs font-bold tracking-wide text-ink-2 uppercase">{t("stepOf", { step: i + 1, total: steps.length })}</p>
        <h2 id="tour-title" className="mt-1 text-lg">
          {t(`${id}.${step.key}.title`)}
        </h2>
        <p id="tour-body" className="mt-1 text-ink">
          {t(`${id}.${step.key}.body`)}
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button type="button" size="sm" variant="secondary" onClick={close}>
            {t("skip")}
          </Button>
          <span className="flex-1" />
          {i > 0 ? (
            <Button type="button" size="sm" variant="secondary" onClick={() => setI(i - 1)}>
              {t("back")}
            </Button>
          ) : null}
          {last ? (
            <Button type="button" size="sm" onClick={close}>
              {t("done")}
            </Button>
          ) : (
            <Button type="button" size="sm" onClick={() => setI(i + 1)}>
              {t("next")}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
