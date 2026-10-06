import { getTranslations, setRequestLocale } from "next-intl/server";

import { SimplePage } from "../simple-page";

export default async function AboutPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("about");
  return (
    <SimplePage locale={locale} title={t("title")}>
      <p>{t("body1")}</p>
      <p>{t("body2")}</p>
      <h2 className="pt-4 text-xl">{t("statusTitle")}</h2>
      <p>{t("statusBody")}</p>
    </SimplePage>
  );
}
