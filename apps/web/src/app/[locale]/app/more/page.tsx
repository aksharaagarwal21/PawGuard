import { getTranslations, setRequestLocale } from "next-intl/server";

import { LanguageSwitcher } from "@/components/language-switcher";
import { Link } from "@/i18n/navigation";
import { SignOutForm } from "@/components/sign-out-form";
import { chooseOrganisation } from "@/lib/auth-actions";
import { visibleNav } from "@/lib/nav";
import { activeMembership, getMe } from "@/lib/session";

/** Mobile "More" menu: everything not in the bottom bar, plus organisation, language and sign out. */
export default async function MorePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("nav");
  const result = await getMe();
  if (result.state !== "ok") return null;
  const active = await activeMembership(result.me);
  if (!active) return null;
  const extra = visibleNav(active.capabilities, active.professional_scopes, active.org_type).filter((i) => !i.mobile);
  const tourHref = active.capabilities.includes("pet.own")
    ? "/app/pets?tour=1"
    : active.org_type === "veterinary_service" && active.capabilities.includes("animal.read")
      ? "/app/clinic?tour=1"
      : null;
  return (
    <div className="mx-auto max-w-xl space-y-8 px-4 py-6">
      <h1 className="text-2xl">{t("more")}</h1>
      {extra.length > 0 ? (
        <ul className="divide-y divide-divider rounded-card border border-divider bg-surface">
          {extra.map((i) => (
            <li key={i.key}>
              <Link
                href={i.href}
                className="flex min-h-12 items-center px-4 font-display font-semibold text-ink no-underline hover:bg-sage"
              >
                {t(i.labelKey)}
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
      {result.me.memberships.length > 1 ? (
        <form action={chooseOrganisation} className="space-y-2">
          <input type="hidden" name="locale" value={locale} />
          <label className="block">
            <span className="font-display text-sm font-semibold">{t("organisation")}</span>
            <select
              name="org_id"
              defaultValue={active.org_id}
              className="mt-1 min-h-11 w-full rounded-control border border-control bg-surface px-2"
            >
              {result.me.memberships.map((m) => (
                <option key={m.org_id} value={m.org_id}>
                  {m.org_name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            className="min-h-11 rounded-control border border-control bg-surface px-4 font-semibold hover:bg-sage"
          >
            {t("switchOrganisation")}
          </button>
        </form>
      ) : null}
      {tourHref ? (
        <section aria-labelledby="help-h" className="space-y-2">
          <h2 id="help-h" className="text-lg">{t("helpMenu")}</h2>
          <ul className="divide-y divide-divider rounded-card border border-divider bg-surface">
            <li>
              <Link href={tourHref} className="flex min-h-12 items-center px-4 font-display font-semibold text-ink no-underline hover:bg-sage">
                {t("showTour")}
              </Link>
            </li>
          </ul>
        </section>
      ) : null}
      <LanguageSwitcher />
      <SignOutForm locale={locale} className="inline-flex min-h-11 items-center gap-2 rounded-control border border-control bg-surface px-4 font-semibold hover:bg-sage" />
    </div>
  );
}
