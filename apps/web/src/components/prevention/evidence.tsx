import type { Schemas } from "@pawguard/api-client";
import { PawPrint } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import { Notice, StatusChip, cn, type ChipKind } from "@pawguard/ui";

import { formatPartialDate } from "@/lib/format";

type Summary = Schemas["VaccinationSummary"];
type VaccState = Schemas["VaccinationOut"]["state"];
type ProfileState = Schemas["AnimalOut"]["profile_state"];

const VACC_CHIP: Record<VaccState, ChipKind> = {
  draft: "draft",
  submitted: "submitted",
  verified: "verified",
  rejected: "rejected",
  needs_correction: "needs_correction",
  superseded: "superseded",
};

const PROFILE_CHIP: Record<ProfileState, ChipKind> = {
  provisional: "provisional",
  reviewed: "reviewed",
  active: "reviewed",
  disputed: "disputed",
  merged_alias: "neutral",
  archived: "neutral",
};

/** Wording comes from DESIGN_SYSTEM.md "Evidence-state wording"; never "vaccinated", "safe" or "unvaccinated". */
export function VaccinationStateChip({ state }: { state: VaccState }) {
  const t = useTranslations("evidence.state");
  return <StatusChip kind={VACC_CHIP[state]}>{t(state)}</StatusChip>;
}

export function ProfileStateChip({ state }: { state: ProfileState }) {
  const t = useTranslations("profileState");
  return <StatusChip kind={PROFILE_CHIP[state]}>{t(state)}</StatusChip>;
}

/** Compact one-line evidence status for lists. */
export function VaccinationSummaryChip({ summary }: { summary: Summary }) {
  const t = useTranslations("evidence.summary");
  const tc = useTranslations("common");
  const locale = useLocale();
  if (summary.status === "verified_record") {
    const date = formatPartialDate(summary.last_verified_on, summary.last_verified_precision, locale, tc("notRecorded"));
    return <StatusChip kind="verified">{t("verified_record", { date })}</StatusChip>;
  }
  if (summary.status === "submitted_only") return <StatusChip kind="submitted">{t("submitted_only")}</StatusChip>;
  return <StatusChip kind="neutral">{t("no_verified_record")}</StatusChip>;
}

/** Full explanation panel for the animal profile. */
export function VaccinationSummaryPanel({ summary }: { summary: Summary }) {
  const t = useTranslations("evidence.summary");
  const tc = useTranslations("common");
  const locale = useLocale();
  const pending = summary.pending_review_count ?? 0;
  if (summary.status === "verified_record") {
    const date = formatPartialDate(summary.last_verified_on, summary.last_verified_precision, locale, tc("notRecorded"));
    return (
      <Notice tone="success" title={t("verified_record", { date })}>
        <p>{t("verifiedExplain")}</p>
        {summary.next_review_on && summary.next_review_source ? (
          <p>
            {t("nextReview", {
              source: summary.next_review_source,
              date: formatPartialDate(summary.next_review_on, "day", locale, tc("notRecorded")),
            })}
          </p>
        ) : null}
        {pending > 0 ? <p>{t("pendingAlso", { count: pending })}</p> : null}
      </Notice>
    );
  }
  if (summary.status === "submitted_only") {
    return (
      <Notice tone="pending" title={t("submitted_only")}>
        <p>{t("submittedExplain", { count: pending })}</p>
      </Notice>
    );
  }
  return (
    <Notice tone="neutral" title={t("no_verified_record")}>
      <p>{t("noneExplain")}</p>
    </Notice>
  );
}

export function AnimalThumb({
  url,
  alt,
  size = "md",
  className,
}: {
  url?: string | null;
  alt: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const dims = { sm: "size-12", md: "size-16", lg: "size-28 md:size-36" }[size];
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element -- short-lived signed URLs from private storage
    return <img src={url} alt={alt} className={cn(dims, "shrink-0 rounded-control bg-sage object-cover", className)} />;
  }
  return (
    <span className={cn(dims, "flex shrink-0 items-center justify-center rounded-control bg-sage text-primary", className)}>
      <PawPrint aria-hidden className="size-1/2 opacity-60" />
      <span className="sr-only">{alt}</span>
    </span>
  );
}
