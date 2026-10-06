import { setRequestLocale } from "next-intl/server";

import { FieldKit } from "./field-kit";

/**
 * Offline field kit. The HTML of this page carries no personal or organisation data (everything is read from this
 * device's storage after the person opts in), so it is the one page the service worker may keep for offline use.
 */
export default async function FieldPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <FieldKit locale={locale} />;
}
