import { ShieldCheck, Wrench } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Card, Notice, StatusChip } from "@pawguard/ui";

import { PageBody } from "@/components/page-header";
import { ClinicBoard } from "@/components/pets/clinic-board";
import { ClinicRecordForm } from "@/components/pets/clinic-record-form";
import { MessagesPanel } from "@/components/notify/messages-panel";
import { WhatsAppDemo } from "@/components/notify/whatsapp-demo";
import { DemoClockControl } from "@/components/pets/demo-clock";
import { WelcomeTour } from "@/components/tour/welcome-tour";
import { Link } from "@/i18n/navigation";
import { pageContext } from "@/lib/page-context";

/** "Demo — Lotus Pet Clinic (fictional)" → "Lotus Pet Clinic" for the heading; the demo label is shown as a chip. */
function shortName(name: string): string {
  return name.replace(/^Demo\s+—\s+/, "").replace(/\s+\(fictional\)$/, "");
}

/** Clinic staff: what needs doing today — verification first, then overdue and due soon. */
export default async function ClinicPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const ctx = await pageContext();
  const t = await getTranslations("clinic");
  const tc = await getTranslations("common");
  const [{ data: d, error }, messages] = await Promise.all([
    ctx.api.GET("/api/v1/clinic/dashboard"),
    ctx.api.GET("/api/v1/clinic/notifications"),
  ]);
  if (!d) return <PageBody><Notice tone="urgent">{error?.error?.message ?? tc("tryAgainLater")}</Notice></PageBody>;
  const canReview = ctx.can("vaccination.review");
  const realToday = new Date().toLocaleDateString("en-CA", { timeZone: ctx.tz });
  const tour = [
    { target: '[data-tour="clinic-tiles"]', key: "tiles" },
    { target: '[data-tour="clinic-queue"]', key: "queue" },
    ...(canReview ? [{ target: '[data-tour="clinic-record"]', key: "record" }] : []),
    ...(d.demo_clock_available ? [{ target: '[data-tour="clinic-demo"]', key: "demo" }] : []),
  ];

  return (
    <PageBody wide>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl md:text-3xl">
            <span className="mb-1 block font-body text-base font-semibold text-ink-2">{t("title")}</span>
            {t("todayAt", { clinic: shortName(ctx.active.org_name) })}
          </h1>
          <p className="mt-1 text-ink-2">{t("intro")}</p>
          <p className="mt-1 text-sm">
            <Link href="/verify" className="inline-flex min-h-11 items-center gap-1.5 font-semibold">
              <ShieldCheck aria-hidden className="size-4" />
              {t("verifyLink")}
            </Link>
          </p>
        </div>
        {ctx.active.org_is_demo ? <StatusChip kind="demo">{t("demoClinic")}</StatusChip> : null}
      </div>

      <Card className="space-y-1">
        <p className="font-display text-xl font-semibold">{t("upToDate", { up: d.up_to_date, total: d.pets_total })}</p>
        <p className="text-sm font-semibold text-ink-2">{t("coverageNote")}</p>
        <p className="text-sm text-ink-2">
          {t("noVerified", { count: d.no_verified_record })} · {t("unverifiedOnly", { count: d.unverified_only })}
        </p>
      </Card>

      <ClinicBoard d={d} canReview={canReview} />

      {canReview && d.pets.length > 0 && d.products.length > 0 ? (
        <section aria-labelledby="record" className="space-y-3 rounded-card border border-divider bg-surface p-4" data-tour="clinic-record">
          <h2 id="record" className="text-lg">{t("record.title")}</h2>
          <p className="text-sm text-ink-2">{t("record.intro")}</p>
          <ClinicRecordForm pets={d.pets} products={d.products} today={realToday} />
        </section>
      ) : null}

      {messages.data ? <MessagesPanel data={messages.data} tz={ctx.tz} demo={d.demo_clock_available} /> : null}

      {d.demo_clock_available ? (
        <section aria-labelledby="demo-tools" className="space-y-3 rounded-card border-2 border-dashed border-control p-4" data-tour="clinic-demo">
          <h2 id="demo-tools" className="flex items-center gap-2 text-lg">
            <Wrench aria-hidden className="size-5 text-ink-2" />
            {t("demoTools")}
          </h2>
          <p className="text-sm text-ink-2">{t("demoToolsIntro")}</p>
          <DemoClockControl offsetDays={d.demo_offset_days} today={d.today} />
          <WhatsAppDemo />
        </section>
      ) : null}
      <WelcomeTour id="clinic" steps={tour} />
    </PageBody>
  );
}
