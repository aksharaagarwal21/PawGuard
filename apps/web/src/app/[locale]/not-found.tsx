import { getTranslations } from "next-intl/server";

import { PublicPage } from "@/components/public-shell";
import { Link } from "@/i18n/navigation";

export default async function NotFound() {
  const t = await getTranslations("errors");
  return (
    <PublicPage locale="en">
      <div className="container-pg py-16">
        <h1 className="text-3xl">{t("notFoundTitle")}</h1>
        <p className="mt-3 text-lg text-ink-2">{t("notFoundBody")}</p>
        <p className="mt-6">
          <Link href="/">{t("home")}</Link>
        </p>
      </div>
    </PublicPage>
  );
}
