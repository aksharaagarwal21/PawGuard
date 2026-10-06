"use client";

import { Globe } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useTransition } from "react";

import { usePathname, useRouter } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";

/** Switches locale and keeps the current page (and its query string) so the user's task is preserved. */
export function LanguageSwitcher({ className }: { className?: string }) {
  const t = useTranslations("common");
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const [pending, startTransition] = useTransition();
  return (
    <label className={`inline-flex items-center gap-2 ${className ?? ""}`}>
      <Globe aria-hidden className="size-4 text-ink-2" />
      <span className="sr-only">{t("language")}</span>
      <select
        value={locale}
        disabled={pending}
        onChange={(e) => {
          const next = e.target.value;
          const search = typeof window !== "undefined" ? window.location.search : "";
          startTransition(() => {
            router.replace(`${pathname}${search}`, { locale: next });
          });
        }}
        className="min-h-11 rounded-control border border-control bg-surface px-2 text-sm"
      >
        {routing.locales.map((l) => (
          <option key={l} value={l}>
            {t(`languageNames.${l}`)}
          </option>
        ))}
      </select>
    </label>
  );
}
