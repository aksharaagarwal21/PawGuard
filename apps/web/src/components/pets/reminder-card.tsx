"use client";

import type { Schemas } from "@pawguard/api-client";
import { AlertTriangle, Bell, CalendarPlus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { Button, Card, cn } from "@pawguard/ui";

import { Link, useRouter } from "@/i18n/navigation";
import { browserApi } from "@/lib/api-browser";
import { formatPartialDate } from "@/lib/format";

import { OwnerRecordForm } from "./owner-record-form";

type Reminder = Schemas["ReminderOut"];

export function ReminderCard({
  reminder,
  products,
  today,
  showPet = true,
}: {
  reminder: Reminder;
  products: { id: string; name: string }[];
  today: string;
  showPet?: boolean;
}) {
  const t = useTranslations("reminders");
  const locale = useLocale();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [doneOpen, setDoneOpen] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const r = reminder;
  const date = formatPartialDate(r.due_on, "day", locale, "");
  const overdue = r.kind === "overdue";

  async function snooze(days: 1 | 3) {
    setBusy(true);
    const { error } = await browserApi.POST("/api/v1/my/reminders/{reminder_id}/snooze", {
      params: { path: { reminder_id: r.id } },
      body: { days },
    });
    setBusy(false);
    if (error) return setMessage(t("actionFailed"));
    setMessage(t("snoozed", { days }));
    router.refresh();
  }

  return (
    <Card className={cn("space-y-3", overdue && "border-urgent")}>
      <div className="flex items-start gap-3">
        {overdue ? (
          <AlertTriangle aria-hidden className="mt-0.5 size-5 shrink-0 text-urgent" />
        ) : (
          <Bell aria-hidden className="mt-0.5 size-5 shrink-0 text-primary" />
        )}
        <div className="min-w-0 space-y-1">
          <p className="font-display font-semibold">
            {showPet ? (
              <Link href={`/app/pets/${r.pet_id}`}>{r.pet_name}</Link>
            ) : null}
            {showPet ? " · " : null}
            {r.vaccine}
          </p>
          <p className={cn("text-sm", overdue && "font-semibold text-urgent")}>
            {overdue
              ? t("overdue", { date, days: -r.days_until_due })
              : r.days_until_due === 0
                ? t("dueToday", { date })
                : t("dueIn", { date, days: r.days_until_due })}
          </p>
          <p className="text-sm text-ink-2">
            {t(`kind.${r.kind}`)} · {r.clinic_name}
          </p>
        </div>
      </div>
      {message ? (
        <p role="status" className="text-sm font-semibold">
          {message}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" onClick={() => setDoneOpen((v) => !v)} aria-expanded={doneOpen}>
          {t("markDone")}
        </Button>
        <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={() => snooze(1)}>
          {t("snooze1")}
        </Button>
        <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={() => snooze(3)}>
          {t("snooze3")}
        </Button>
        <Button asChild size="sm" variant="secondary">
          <a href={`/api/v1/my/reminders/${r.id}/calendar.ics`} download>
            <CalendarPlus aria-hidden className="size-4" />
            {t("addToCalendar")}
          </a>
        </Button>
      </div>
      {doneOpen ? (
        <div className="rounded-control border border-divider p-3">
          <OwnerRecordForm
            petId={r.pet_id}
            clinicOrgId={r.clinic_org_id}
            products={products}
            today={today}
            reminder={{ id: r.id, vaccine: r.vaccine }}
          />
        </div>
      ) : null}
      <details className="rounded-control border border-dashed border-control p-3 text-sm">
        <summary className="cursor-pointer font-semibold">{t("previewTitle")}</summary>
        <p className="mt-2 font-semibold text-ink-2">{t("previewNote")}</p>
        <dl className="mt-2 space-y-2">
          <div>
            <dt className="font-semibold">{t("previewEmail")}</dt>
            <dd>
              <p className="font-semibold">{r.preview.email_subject}</p>
              <p className="whitespace-pre-line">{r.preview.email_body}</p>
            </dd>
          </div>
          <div>
            <dt className="font-semibold">{t("previewSms")}</dt>
            <dd>{r.preview.sms}</dd>
          </div>
        </dl>
      </details>
    </Card>
  );
}
