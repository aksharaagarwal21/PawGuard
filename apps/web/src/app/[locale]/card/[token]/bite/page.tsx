import type { Schemas } from "@pawguard/api-client";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Notice } from "@pawguard/ui";

import { BiteShell } from "@/components/bite/bite-shell";
import { CertificateCheck } from "@/components/bite/certificate-check";
import { FirstAid } from "@/components/bite/first-aid";
import { BiteReportForm } from "@/components/bite/report-form";
import { formatPartialDate } from "@/lib/format";
import { serverEnv } from "@/lib/server-env";

export const metadata: Metadata = { robots: { index: false }, referrer: "no-referrer" };

async function load(token: string): Promise<Schemas["BitePetOut"] | null> {
  try {
    const r = await fetch(new URL(`/api/v1/public/cards/${encodeURIComponent(token)}/bite`, serverEnv().PAWGUARD_API_INTERNAL_URL), {
      cache: "no-store",
    });
    return r.ok ? ((await r.json()) as Schemas["BitePetOut"]) : null;
  } catch {
    return null;
  }
}

/** Bite mode (from the collar QR): 1. first aid, 2. the pet's vaccination record with the signature check,
 *  3. report the bite / doctor link. No account, no photo, no questions before first aid. */
export default async function BiteModePage({ params }: { params: Promise<{ locale: string; token: string }> }) {
  const { locale, token } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("bite");
  const pet = await load(token);
  const fmt = (d: string | null | undefined) => formatPartialDate(d, "day", locale, "—");
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
  return (
    <BiteShell>
      <FirstAid headingLevel={1} />
      {pet ? (
        <>
          <section aria-labelledby="status-h" className="space-y-2 rounded-card border border-divider bg-surface p-5" data-testid="bite-status">
            <h2 id="status-h" className="text-xl">
              {t("status.title")}
            </h2>
            <p className="font-semibold">
              {pet.pet_name} · {pet.clinic_name}
            </p>
            {pet.rabies ? (
              <>
                <p>
                  {t("status.given", { vaccine: pet.rabies.vaccine ?? "—", date: fmt(pet.rabies.given_on) })}{" "}
                  {pet.rabies.next_due_on ? t("status.nextDue", { date: fmt(pet.rabies.next_due_on) }) : null}
                </p>
                <CertificateCheck qr={pet.rabies.certificate} />
              </>
            ) : (
              <p className="font-semibold">{t("status.none")}</p>
            )}
            <p className="font-semibold">{t("status.showDoctor")}</p>
            <p className="text-sm text-ink-2">{t("status.notAGuarantee")}</p>
          </section>
          <BiteReportForm cardToken={token} today={today} />
        </>
      ) : (
        <Notice tone="neutral">{t("share.notFoundBody")}</Notice>
      )}
    </BiteShell>
  );
}
