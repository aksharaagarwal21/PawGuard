import type { Schemas } from "@pawguard/api-client";
import { AlertTriangle, CalendarClock, CheckCircle2, CircleDashed, FileQuestion, PawPrint } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import { cn } from "@pawguard/ui";

import { formatPartialDate } from "@/lib/format";

type PetStatus = Schemas["PetStatusOut"];
type Verification = Schemas["TimelineEntryOut"]["verification"];

const STATUS_STYLE: Record<PetStatus["status"], { cls: string; Icon: typeof CheckCircle2 }> = {
  up_to_date: { cls: "bg-sage text-ink", Icon: CheckCircle2 },
  due_soon: { cls: "bg-sand text-ink", Icon: CalendarClock },
  overdue: { cls: "border border-urgent bg-surface text-urgent", Icon: AlertTriangle },
  unverified_record: { cls: "bg-sand text-ink", Icon: FileQuestion },
  // Never shown as "unvaccinated" or "overdue": we simply have no verified record.
  no_verified_record: { cls: "border border-control bg-surface text-ink", Icon: CircleDashed },
};

/** Pet vaccination status: icon + text, never colour alone. */
export function PetStatusChip({ status, className }: { status: PetStatus; className?: string }) {
  const t = useTranslations("pets.status");
  const { cls, Icon } = STATUS_STYLE[status.status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-display text-xs font-semibold whitespace-nowrap",
        cls,
        className,
      )}
    >
      <Icon aria-hidden className="size-3.5" />
      {t(status.status)}
    </span>
  );
}

/** One-line explanation of the next due date and where it came from. */
export function NextDueLine({ status }: { status: PetStatus }) {
  const t = useTranslations("pets");
  const locale = useLocale();
  if (!status.next_due_on) {
    if (status.status === "no_verified_record") return <p className="text-sm text-ink-2">{t("noVerifiedHint")}</p>;
    if (status.status === "unverified_record") return <p className="text-sm text-ink-2">{t("unverifiedHint")}</p>;
    return <p className="text-sm text-ink-2">{t("noDueDate")}</p>;
  }
  const date = formatPartialDate(status.next_due_on, "day", locale, "");
  const days = status.days_until_due ?? 0;
  return (
    <div className="text-sm">
      <p>
        {days < 0
          ? t("wasDue", { vaccine: status.vaccine ?? "", date, days: -days })
          : days === 0
            ? t("dueToday", { vaccine: status.vaccine ?? "", date })
            : t("dueIn", { vaccine: status.vaccine ?? "", date, days })}
      </p>
      <DueSource source={status.next_due_source} />
    </div>
  );
}

export function DueSource({ source }: { source: string | null | undefined }) {
  const t = useTranslations("pets");
  if (source === "demo_template") return <p className="text-sm font-semibold text-ink-2">{t("templateLabel")}</p>;
  if (source === "vet") return <p className="text-sm text-ink-2">{t("dueFromVet")}</p>;
  return null;
}

const VERIFICATION_STYLE: Record<Verification, string> = {
  verified_by_vet: "bg-sage text-ink",
  entered_by_owner_unverified: "bg-sand text-ink",
  submitted_unverified: "bg-sand text-ink",
  needs_correction: "bg-sand text-ink",
  rejected: "border border-urgent bg-surface text-urgent",
  superseded: "border border-control bg-surface text-ink-2",
};

export function VerificationChip({ value }: { value: Verification }) {
  const t = useTranslations("pets.verification");
  const Icon = value === "verified_by_vet" ? CheckCircle2 : value === "rejected" ? AlertTriangle : FileQuestion;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-display text-xs font-semibold whitespace-nowrap",
        VERIFICATION_STYLE[value],
      )}
    >
      <Icon aria-hidden className="size-3.5" />
      {t(value)}
    </span>
  );
}

export function PetAvatar({ url, name, size = "md" }: { url?: string | null; name: string; size?: "md" | "lg" }) {
  const cls = size === "lg" ? "size-24" : "size-14";
  return url ? (
    // eslint-disable-next-line @next/next/no-img-element -- short-lived signed thumbnail
    <img src={url} alt="" className={cn(cls, "shrink-0 rounded-card border border-divider object-cover")} />
  ) : (
    <div
      aria-hidden
      title={name}
      className={cn(cls, "flex shrink-0 items-center justify-center rounded-card border border-divider bg-sage text-primary")}
    >
      <PawPrint className="size-1/2" />
    </div>
  );
}
