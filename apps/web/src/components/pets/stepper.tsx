"use client";

import { useTranslations } from "next-intl";

/** "Step 2 of 3" with a progress bar and the step's name. The bar's change is animated gently (motion-safe). */
export function StepProgress({ step, total, title }: { step: number; total: number; title: string }) {
  const t = useTranslations("pets.stepper");
  return (
    <div className="space-y-2">
      <p className="text-sm font-semibold text-ink-2">
        {t("stepOf", { step, total })} · <span className="text-ink">{title}</span>
      </p>
      <div
        role="progressbar"
        aria-label={t("progressLabel")}
        aria-valuemin={1}
        aria-valuemax={total}
        aria-valuenow={step}
        aria-valuetext={t("stepOf", { step, total })}
        className="h-2 overflow-hidden rounded-full bg-sage"
      >
        <div
          className="h-full rounded-full bg-primary motion-safe:transition-[width] motion-safe:duration-200 motion-safe:ease-calm"
          style={{ width: `${(step / total) * 100}%` }}
        />
      </div>
    </div>
  );
}

/** Review list shown before saving. */
export function ReviewList({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="divide-y divide-divider rounded-control border border-divider bg-surface">
      {rows.map(([k, v]) => (
        <div key={k} className="grid gap-1 p-3 sm:grid-cols-[10rem_1fr]">
          <dt className="text-sm font-semibold text-ink-2">{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}
