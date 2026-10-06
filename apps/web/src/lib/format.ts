/**
 * Display helpers. Date-only values are formatted in UTC so a calendar date never shifts across timezones;
 * partial dates are shown at their recorded precision (never padded to a fake day).
 */
export type DatePrecision = "exact_time" | "day" | "month" | "year" | "unknown";

const LOCALE_TAG: Record<string, string> = { en: "en-IN", ta: "ta-IN", hi: "hi-IN" };

export function localeTag(locale: string): string {
  return LOCALE_TAG[locale] ?? "en-IN";
}

export function formatPartialDate(
  value: string | null | undefined,
  precision: DatePrecision | string | null | undefined,
  locale: string,
  unknownLabel: string,
): string {
  if (!value || precision === "unknown" || !precision) return unknownLabel;
  const d = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  const tag = localeTag(locale);
  if (precision === "year") return new Intl.DateTimeFormat(tag, { year: "numeric", timeZone: "UTC" }).format(d);
  if (precision === "month")
    return new Intl.DateTimeFormat(tag, { month: "long", year: "numeric", timeZone: "UTC" }).format(d);
  return new Intl.DateTimeFormat(tag, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(d);
}

export function formatDateTime(value: string | null | undefined, locale: string, timeZone: string): string {
  if (!value) return "";
  return new Intl.DateTimeFormat(localeTag(locale), {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
  }).format(new Date(value));
}

/** Calendar-day number of an instant as seen in `timeZone` (for comparing dates, not elapsed hours). */
function dayNumber(d: Date, timeZone: string): number {
  const [y, m, day] = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" })
    .format(d)
    .split("-")
    .map(Number);
  return Date.UTC(y!, m! - 1, day!) / 86_400_000;
}

/**
 * "today" / "3 days ago" by calendar day in the organisation's timezone (a sighting recorded today at day precision
 * is stored as local midnight and must not read as "yesterday"), falling back to a date beyond 60 days.
 */
export function relativeDays(value: string | null | undefined, locale: string, timeZone = "UTC"): string | null {
  if (!value) return null;
  const then = new Date(value);
  const days = dayNumber(then, timeZone) - dayNumber(new Date(), timeZone);
  if (Math.abs(days) > 60) {
    return new Intl.DateTimeFormat(localeTag(locale), { day: "numeric", month: "short", year: "numeric", timeZone }).format(then);
  }
  return new Intl.RelativeTimeFormat(localeTag(locale), { numeric: "auto" }).format(days, "day");
}

export function todayIso(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
