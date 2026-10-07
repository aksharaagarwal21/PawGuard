"use client";

import { CheckCircle2, CircleHelp, ShieldAlert } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { loadCachedLists, refreshLists } from "@/lib/verify/lists-store";
import { verifyCertificate, type Outcome } from "@/lib/verify/verify";

/** The Part 1 signature check, inline: runs in the browser against the root-signed lists (cached; refreshed when
 *  online). Shows only "checked" or "could not be confirmed" — never anything about health. */
export function CertificateCheck({ qr }: { qr: string | null | undefined }) {
  const t = useTranslations("bite.status");
  const [outcome, setOutcome] = useState<Outcome | "checking" | null>(qr ? "checking" : null);

  useEffect(() => {
    if (!qr) return;
    let cancelled = false;
    void (async () => {
      let lists = loadCachedLists();
      if (navigator.onLine) {
        try {
          lists = await refreshLists(lists);
        } catch {
          /* keep cached lists */
        }
      }
      const result = await verifyCertificate(qr, lists.trust, lists.revocations, new Date().toLocaleDateString("en-CA"));
      if (!cancelled) setOutcome(result);
    })();
    return () => {
      cancelled = true;
    };
  }, [qr]);

  if (!qr) return <p className="text-sm text-ink-2">{t("noCertificate")}</p>;
  if (outcome === "checking" || outcome === null)
    return (
      <p role="status" className="text-sm text-ink-2">
        {t("checking")}
      </p>
    );
  if (outcome.status === "genuine")
    return (
      <p role="status" className="flex items-start gap-2 text-sm font-semibold" data-testid="bite-cert-genuine">
        <CheckCircle2 aria-hidden className="mt-0.5 size-4 shrink-0 text-primary" />
        {t("genuine", { clinic: outcome.clinicName })}
      </p>
    );
  if (outcome.status === "no_lists")
    return (
      <p role="status" className="flex items-start gap-2 text-sm">
        <CircleHelp aria-hidden className="mt-0.5 size-4 shrink-0" />
        {t("noLists")}
      </p>
    );
  return (
    <p role="status" className="flex items-start gap-2 text-sm font-semibold text-urgent" data-testid="bite-cert-unconfirmed">
      <ShieldAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
      {t("notConfirmed")}
    </p>
  );
}
