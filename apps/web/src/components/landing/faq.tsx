import { ChevronDown } from "lucide-react";
import { useTranslations } from "next-intl";

const QUESTIONS = ["sms", "dueDate", "lostCertificate", "privacy", "noVerified"] as const;

/** FAQ as native disclosure widgets: keyboard and screen-reader friendly without script. */
export function Faq() {
  const t = useTranslations("faq");
  return (
    <div className="divide-y divide-divider rounded-card border border-divider bg-surface">
      {QUESTIONS.map((q) => (
        <details key={q} className="group p-4 [&_summary::-webkit-details-marker]:hidden">
          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 font-display font-semibold">
            {t(`${q}.q`)}
            <ChevronDown aria-hidden className="size-5 shrink-0 text-ink-2 transition-transform duration-200 ease-calm group-open:rotate-180" />
          </summary>
          <p className="mt-2 max-w-prose text-ink-2">{t(`${q}.a`)}</p>
        </details>
      ))}
    </div>
  );
}
