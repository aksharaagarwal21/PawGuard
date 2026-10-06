import type { Schemas } from "@pawguard/api-client";
import { ArrowRight, CircleCheck, Lightbulb } from "lucide-react";

import { cn } from "@pawguard/ui";

import { Link } from "@/i18n/navigation";

type Pet = Schemas["PetCardOut"];
export type NextStep = {
  tone: "urgent" | "soon" | "info" | "done";
  title: string;
  body: string;
  actions: { href: string; label: string; primary?: boolean }[];
};

type T = (key: string, values?: Record<string, string | number>) => string;

/** The single most useful thing to do now, across the given pets (most urgent first). */
export function pickNextStep(pets: Pet[], t: T): NextStep {
  const by = (s: string) => pets.filter((p) => p.status.status === s);
  const overdue = by("overdue").sort((a, b) => (a.status.days_until_due ?? 0) - (b.status.days_until_due ?? 0))[0];
  if (overdue) {
    return {
      tone: "urgent",
      title: t("overdueTitle", { name: overdue.name, vaccine: overdue.status.vaccine ?? "" }),
      body: t("overdueBody", { clinic: overdue.clinic_name }),
      actions: [
        { href: "/app/reminders", label: t("markDone"), primary: true },
        { href: `/app/pets/${overdue.id}`, label: t("openPet", { name: overdue.name }) },
      ],
    };
  }
  const soon = by("due_soon").sort((a, b) => (a.status.days_until_due ?? 0) - (b.status.days_until_due ?? 0))[0];
  if (soon) {
    return {
      tone: "soon",
      title: t("soonTitle", { name: soon.name, days: soon.status.days_until_due ?? 0 }),
      body: t("soonBody", { clinic: soon.clinic_name }),
      actions: [
        { href: "/app/reminders", label: t("seeReminder"), primary: true },
        { href: `/app/pets/${soon.id}`, label: t("openPet", { name: soon.name }) },
      ],
    };
  }
  const none = by("no_verified_record")[0];
  if (none) {
    return {
      tone: "info",
      title: t("noneTitle", { name: none.name }),
      body: t("noneBody"),
      actions: [{ href: `/app/pets/${none.id}`, label: t("addPast"), primary: true }],
    };
  }
  const waiting = pets.find((p) => p.awaiting_verification > 0);
  if (waiting) {
    return {
      tone: "info",
      title: t("waitingTitle", { name: waiting.name }),
      body: t("waitingBody", { clinic: waiting.clinic_name }),
      actions: [{ href: `/app/pets/${waiting.id}`, label: t("openPet", { name: waiting.name }) }],
    };
  }
  return { tone: "done", title: t("doneTitle"), body: t("doneBody"), actions: [] };
}

const TONE = {
  urgent: "border-urgent bg-urgent-soft",
  soon: "border-sand bg-sand",
  info: "border-sky bg-sky",
  done: "border-sage bg-sage",
} as const;

/** "Next step" box: one clear action, explained in plain words. */
export function NextStepCard({ step, label }: { step: NextStep; label: string }) {
  const Icon = step.tone === "done" ? CircleCheck : Lightbulb;
  return (
    <section aria-label={label} data-tour="next-step" className={cn("rounded-card border-2 p-5", TONE[step.tone])}>
      <p className="flex items-center gap-1.5 text-xs font-bold tracking-wide text-ink-2 uppercase">
        <Icon aria-hidden className={cn("size-4", step.tone === "urgent" ? "text-urgent" : "text-primary")} />
        {label}
      </p>
      <p className="mt-2 font-display text-lg font-semibold">{step.title}</p>
      <p className="mt-1 text-ink">{step.body}</p>
      {step.actions.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {step.actions.map((a) => (
            <Link
              key={a.href + a.label}
              href={a.href}
              className={cn(
                "inline-flex min-h-11 items-center gap-1.5 rounded-control px-4 font-display text-sm font-semibold no-underline",
                a.primary ? "bg-primary text-white hover:bg-primary-hover" : "border border-control bg-surface text-ink hover:bg-sage",
              )}
            >
              {a.label}
              {a.primary ? <ArrowRight aria-hidden className="size-4" /> : null}
            </Link>
          ))}
        </div>
      ) : null}
    </section>
  );
}

/** "due in 5 days", "12 days overdue", "next dose in 8 months" — plain words for a due date. */
export function dueWords(days: number | null | undefined, t: T): string | null {
  if (days === null || days === undefined) return null;
  if (days < 0) return t("overdueDays", { count: -days });
  if (days === 0) return t("dueToday");
  if (days <= 45) return t("dueInDays", { count: days });
  return t("dueInMonths", { count: Math.round(days / 30.4) });
}
