import type { Schemas } from "@pawguard/api-client";
import { AlertTriangle, Mail, Phone } from "lucide-react";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Notice } from "@pawguard/ui";

import { BiteShell } from "@/components/bite/bite-shell";
import { CertificateCheck } from "@/components/bite/certificate-check";
import { DoctorLinks } from "@/components/bite/doctor-links";
import { FirstAid } from "@/components/bite/first-aid";
import { ObservationTimeline } from "@/components/bite/timeline";
import { formatDateTime, formatPartialDate } from "@/lib/format";
import { serverEnv } from "@/lib/server-env";

export const metadata: Metadata = { robots: { index: false }, referrer: "no-referrer" };

async function load(token: string): Promise<Schemas["ShareViewOut"] | null> {
  try {
    const r = await fetch(new URL(`/api/v1/public/bites/${encodeURIComponent(token)}`, serverEnv().PAWGUARD_API_INTERNAL_URL), {
      cache: "no-store",
    });
    return r.ok ? ((await r.json()) as Schemas["ShareViewOut"]) : null;
  } catch {
    return null;
  }
}

/** Private page behind the reporter's link (first aid on top, timeline, doctor links) or a doctor link (read-only).
 *  Nothing about the owner; never says or implies that treatment can be skipped. */
export default async function SharePage({ params }: { params: Promise<{ locale: string; token: string }> }) {
  const { locale, token } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("bite");
  const v = await load(token);
  if (!v) {
    return (
      <BiteShell>
        <FirstAid headingLevel={2} />
        <Notice tone="neutral" title={t("share.notFoundTitle")}>
          <p>{t("share.notFoundBody")}</p>
        </Notice>
      </BiteShell>
    );
  }
  const fmt = (d: string | null | undefined) => formatPartialDate(d, "day", locale, "—");
  const doctor = v.purpose === "doctor";
  return (
    <BiteShell>
      {doctor ? null : <FirstAid headingLevel={2} />}
      <h1 className="text-2xl">{doctor ? t("share.doctorTitle", { reference: v.reference }) : t("share.reporterTitle", { reference: v.reference })}</h1>
      {doctor ? <Notice tone="info">{t("share.doctorNote")}</Notice> : null}
      {v.observation.urgent ? (
        <p role="alert" className="flex items-start gap-2 rounded-card border-l-8 border-urgent bg-urgent-soft p-4 text-lg font-semibold text-urgent" data-testid="urgent-banner">
          <AlertTriangle aria-hidden className="mt-1 size-5 shrink-0" />
          {t("share.urgent")}
        </p>
      ) : null}
      <section className="space-y-1">
        <p className="font-semibold">
          {t("share.biteOn", { date: fmt(v.bite_date) })}
          {v.bite_time ? ` ${t("share.biteAt", { time: v.bite_time })}` : ""}
        </p>
        <p>{v.bitten === "animal" ? t("share.bittenAnimal") : t("share.bittenPerson")}</p>
      </section>
      <section aria-labelledby="rec-h" className="space-y-2 rounded-card border border-divider bg-surface p-5">
        <h2 id="rec-h" className="text-xl">
          {t("status.title")}
        </h2>
        <p className="font-semibold">
          {v.pet_name} · {v.clinic_name}
        </p>
        {v.rabies ? (
          <>
            <p>
              {t("status.given", { vaccine: v.rabies.vaccine ?? "—", date: fmt(v.rabies.given_on) })}{" "}
              {v.rabies.next_due_on ? t("status.nextDue", { date: fmt(v.rabies.next_due_on) }) : null}
            </p>
            <CertificateCheck qr={v.rabies.certificate} />
          </>
        ) : (
          <p className="font-semibold">{t("status.none")}</p>
        )}
        <p className="font-semibold">{t("status.showDoctor")}</p>
      </section>
      <ObservationTimeline obs={v.observation} pet={v.pet_name} />
      <section aria-labelledby="contact-h" className="space-y-1">
        <h2 id="contact-h" className="text-lg">
          {t("share.contactTitle")}
        </h2>
        <p>{t("share.contactClinic", { clinic: v.clinic_name })}</p>
        <p className="flex flex-wrap gap-4">
          {v.clinic_email ? (
            <a href={`mailto:${v.clinic_email}`} className="inline-flex min-h-11 items-center gap-1.5">
              <Mail aria-hidden className="size-4" /> {v.clinic_email}
            </a>
          ) : null}
          {v.clinic_phone ? (
            <a href={`tel:${v.clinic_phone}`} className="inline-flex min-h-11 items-center gap-1.5">
              <Phone aria-hidden className="size-4" /> {v.clinic_phone}
            </a>
          ) : null}
        </p>
      </section>
      {!doctor && v.doctor_links ? <DoctorLinks token={token} links={v.doctor_links} tz="Asia/Kolkata" /> : null}
      <p className="text-sm text-ink-2">
        {t("share.keepPrivate")} {t("share.expires", { date: formatDateTime(v.expires_at, locale, "Asia/Kolkata") })}
      </p>
      {v.is_demo ? <p className="text-sm font-semibold">{t("share.demo")}</p> : null}
    </BiteShell>
  );
}
