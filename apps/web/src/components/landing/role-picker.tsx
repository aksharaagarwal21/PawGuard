"use client";

import { Check, Dog, Stethoscope, Users } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { cn } from "@pawguard/ui";

import { Link } from "@/i18n/navigation";

export const ROLES = ["owner", "clinic", "volunteer"] as const;
export type RoleKey = (typeof ROLES)[number];
const ICONS = { owner: Dog, clinic: Stethoscope, volunteer: Users } as const;

type DemoRow = { name: string; role: string; tryFirst: string; group: RoleKey };

/**
 * "Choose how you'll use PawGuard": three selectable cards (a radio group). The choice highlights the matching demo
 * accounts below and the hint next to the continue button. Nothing is stored.
 */
export function RolePicker({ demoRows }: { demoRows: DemoRow[] }) {
  const t = useTranslations("welcome");
  const [role, setRole] = useState<RoleKey>("owner");
  return (
    <>
      <section aria-labelledby="choose" className="space-y-4">
        <h2 id="choose" className="text-xl">{t("chooseTitle")}</h2>
        <p className="text-ink-2">{t("chooseIntro")}</p>
        <fieldset>
          <legend className="sr-only">{t("chooseTitle")}</legend>
          <div className="grid gap-4 md:grid-cols-3">
            {ROLES.map((r) => {
              const Icon = ICONS[r];
              const selected = role === r;
              return (
                <label
                  key={r}
                  className={cn(
                    "relative flex cursor-pointer flex-col gap-3 rounded-card border-2 bg-surface p-5 motion-safe:transition-colors motion-safe:duration-150",
                    selected ? "border-primary bg-sage/40" : "border-divider hover:border-control",
                  )}
                >
                  <input
                    type="radio"
                    name="role"
                    value={r}
                    checked={selected}
                    onChange={() => setRole(r)}
                    className="peer sr-only"
                  />
                  <span className="flex items-center justify-between gap-2">
                    <span className="flex size-11 items-center justify-center rounded-full bg-sage text-primary">
                      <Icon aria-hidden className="size-5" />
                    </span>
                    {selected ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-primary px-2.5 py-0.5 text-xs font-semibold text-white">
                        <Check aria-hidden className="size-3.5" />
                        {t("selected")}
                      </span>
                    ) : null}
                  </span>
                  <span className="font-display text-lg font-semibold">{t(`roles.${r}.title`)}</span>
                  <span className="text-sm font-semibold">{t("youCan")}</span>
                  <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">
                    {(["one", "two", "three"] as const).map((b) => (
                      <li key={b}>{t(`roles.${r}.${b}`)}</li>
                    ))}
                  </ul>
                  <span className="rounded-control bg-sand p-2.5 text-sm">
                    <span className="font-semibold">{t("haveReady")}</span> {t(`roles.${r}.ready`)}
                  </span>
                  <span aria-hidden className="pointer-events-none absolute inset-0 rounded-card peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-focus" />
                </label>
              );
            })}
          </div>
        </fieldset>
      </section>

      <section aria-labelledby="accounts" className="space-y-3">
        <h2 id="accounts" className="text-xl">{t("accountsTitle")}</h2>
        <div className="overflow-x-auto rounded-card border border-divider bg-surface" tabIndex={0} role="region" aria-labelledby="accounts">
          <table className="w-full min-w-[34rem] text-left text-sm">
            <thead>
              <tr className="border-b border-divider">
                <th scope="col" className="p-3">{t("colName")}</th>
                <th scope="col" className="p-3">{t("colRole")}</th>
                <th scope="col" className="p-3">{t("colTry")}</th>
              </tr>
            </thead>
            <tbody>
              {demoRows.map((d) => (
                <tr key={d.name} className={cn("border-b border-divider last:border-0", d.group === role && "bg-sage/60")}>
                  <th scope="row" className="p-3 font-display font-semibold">
                    {d.name}
                    {d.group === role ? <span className="sr-only"> ({t("selected")})</span> : null}
                  </th>
                  <td className="p-3">{d.role}</td>
                  <td className="p-3 text-ink-2">{d.tryFirst}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3 rounded-card bg-sage p-5">
        <Link
          href="/sign-in"
          aria-label={t("continueLabel")}
          className="inline-flex min-h-12 items-center justify-center rounded-control bg-primary px-6 font-display text-base font-semibold text-white no-underline hover:bg-primary-hover"
        >
          {t("continue")}
        </Link>
        <p className="text-sm">{t(`continueHint.${role}`)}</p>
      </div>
    </>
  );
}
