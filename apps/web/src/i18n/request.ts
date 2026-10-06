import { hasLocale } from "next-intl";
import { getRequestConfig } from "next-intl/server";

import { routing } from "./routing";

type Messages = Record<string, unknown>;

/** English is the fallback for keys a locale has not translated yet (the UI labels such content). */
function deepMerge(base: Messages, over: Messages): Messages {
  const out: Messages = { ...base };
  for (const [k, v] of Object.entries(over)) {
    const b = out[k];
    out[k] =
      v && typeof v === "object" && !Array.isArray(v) && b && typeof b === "object"
        ? deepMerge(b as Messages, v as Messages)
        : v;
  }
  return out;
}

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested) ? requested : routing.defaultLocale;
  const en = (await import("../../messages/en.json")).default as Messages;
  const messages =
    locale === "en" ? en : deepMerge(en, (await import(`../../messages/${locale}.json`)).default as Messages);
  // Display timezone for public pages; signed-in views use the organisation's configured timezone.
  return { locale, messages, timeZone: process.env.PAWGUARD_DEFAULT_TIMEZONE ?? "UTC" };
});
