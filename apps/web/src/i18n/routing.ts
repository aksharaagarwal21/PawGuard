import { defineRouting } from "next-intl/routing";

export const locales = ["en", "ta", "hi"] as const;
export type Locale = (typeof locales)[number];

export const routing = defineRouting({
  locales,
  defaultLocale: "en",
  localePrefix: "always",
});
