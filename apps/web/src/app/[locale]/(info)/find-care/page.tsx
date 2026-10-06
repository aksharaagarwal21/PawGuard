import { getTranslations, setRequestLocale } from "next-intl/server";

import { Notice } from "@pawguard/ui";

import { Link } from "@/i18n/navigation";

import { SimplePage } from "../simple-page";

/** No facility directory yet: say so plainly rather than show unverified clinics. */
export default async function FindCarePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("findCare");
  return (
    <SimplePage locale={locale} title={t("title")}>
      <p>{t("body")}</p>
      <Notice tone="info" title={t("meanwhileTitle")}>
        <p>{t("meanwhileBody")}</p>
      </Notice>
      <p>
        <Link href="/help">{t("helpLink")}</Link>
      </p>
    </SimplePage>
  );
}
