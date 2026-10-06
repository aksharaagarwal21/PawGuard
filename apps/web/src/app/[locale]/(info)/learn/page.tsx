import { getTranslations, setRequestLocale } from "next-intl/server";

import { Link } from "@/i18n/navigation";

import { SimplePage } from "../simple-page";

export default async function LearnPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("learn");
  return (
    <SimplePage locale={locale} title={t("title")}>
      <p>{t("body")}</p>
      <p>
        <Link href="/help">{t("helpLink")}</Link>
      </p>
    </SimplePage>
  );
}
