"use client";

import { Check, ClipboardCopy, ShieldCheck } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

/** Sample certificate shortcuts: open it in the verifier (code in the URL fragment, never sent to the server) or copy
 *  the exact text (selecting it on the page can merge double spaces, which Base45 uses). */
export function SampleActions({ qr }: { qr: string }) {
  const t = useTranslations("verify.samples");
  const locale = useLocale();
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex flex-wrap gap-2">
      <a
        href={`/${locale}/verify#qr=${encodeURIComponent(qr)}`}
        className="inline-flex min-h-11 items-center gap-2 rounded-control bg-primary px-3 text-sm font-semibold text-white no-underline"
      >
        <ShieldCheck aria-hidden className="size-4" />
        {t("open")}
      </a>
      <button
        type="button"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(qr);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 2500);
          } catch {
            setCopied(false);
          }
        }}
        className="inline-flex min-h-11 items-center gap-2 rounded-control border border-divider px-3 text-sm font-semibold"
      >
        {copied ? <Check aria-hidden className="size-4 text-primary" /> : <ClipboardCopy aria-hidden className="size-4" />}
        <span aria-live="polite">{copied ? t("copied") : t("copy")}</span>
      </button>
    </div>
  );
}
