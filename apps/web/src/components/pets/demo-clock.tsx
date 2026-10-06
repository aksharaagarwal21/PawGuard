"use client";

import { CalendarClock } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { Button, Card } from "@pawguard/ui";

import { useRouter } from "@/i18n/navigation";
import { browserApi } from "@/lib/api-browser";
import { formatPartialDate } from "@/lib/format";

/** Staff-only, demo organisations only: move "today" for reminders and status to show the reminder schedule. */
export function DemoClockControl({ offsetDays, today }: { offsetDays: number; today: string }) {
  const t = useTranslations("demoClock");
  const locale = useLocale();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  async function set(days: number) {
    setBusy(true);
    setError(false);
    const { error: e } = await browserApi.PUT("/api/v1/clinic/demo-clock", { body: { offset_days: days } });
    setBusy(false);
    if (e) return setError(true);
    router.refresh();
  }

  return (
    <Card className="space-y-3 border-dashed">
      <div className="flex items-start gap-2">
        <CalendarClock aria-hidden className="mt-0.5 size-5 shrink-0 text-primary" />
        <div>
          <p className="font-display font-semibold">{t("title")}</p>
          <p className="text-sm text-ink-2">{t("body")}</p>
          <p className="mt-1 text-sm font-semibold" role="status">
            {t("current", { date: formatPartialDate(today, "day", locale, ""), days: offsetDays })}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {[1, 7].map((d) => (
          <Button key={d} type="button" size="sm" variant="secondary" disabled={busy} onClick={() => set(Math.min(offsetDays + d, 400))}>
            {t("advance", { days: d })}
          </Button>
        ))}
        <Button type="button" size="sm" variant="secondary" disabled={busy || offsetDays === 0} onClick={() => set(0)}>
          {t("reset")}
        </Button>
      </div>
      {error ? <p className="text-sm font-semibold text-urgent">{t("failed")}</p> : null}
    </Card>
  );
}
