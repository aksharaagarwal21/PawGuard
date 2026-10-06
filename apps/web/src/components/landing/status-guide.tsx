import { useTranslations } from "next-intl";

import { PetStatusChip } from "@/components/pets/status";

const ROWS = ["up_to_date", "due_soon", "overdue", "unverified_record", "no_verified_record"] as const;

/** "What the colours mean": every status with its chip (icon + text + colour) and one plain sentence. */
export function StatusGuide() {
  const t = useTranslations("statusGuide");
  return (
    <ul className="divide-y divide-divider rounded-card border border-divider bg-surface">
      {ROWS.map((s) => (
        <li key={s} className="grid gap-2 p-4 sm:grid-cols-[13rem_1fr] sm:items-center">
          <span>
            <PetStatusChip status={{ status: s }} />
          </span>
          <p className="text-ink">{t(s)}</p>
        </li>
      ))}
    </ul>
  );
}
