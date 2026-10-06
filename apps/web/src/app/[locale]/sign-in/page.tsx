import { createApiClient } from "@pawguard/api-client";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Card, Notice } from "@pawguard/ui";

import { PublicPage } from "@/components/public-shell";
import { Link } from "@/i18n/navigation";
import { demoSignIn } from "@/lib/auth-actions";
import { serverEnv } from "@/lib/server-env";

import { SignInForm } from "./sign-in-form";

/** Demo accounts for the pet-vaccination topic, shown first (fictional; seed/accounts.py). */
const PET_EMAILS = new Set(["owner.neha@example.org", "vet.kiran@example.org", "clinic.asha@example.org", "clinic.vikram@example.org"]);

async function demoAccounts() {
  const env = serverEnv();
  if (!env.demoMode) return [];
  try {
    const { data } = await createApiClient({ baseUrl: env.PAWGUARD_API_INTERNAL_URL }).GET("/api/v1/demo/accounts", {
      cache: "no-store",
    });
    return data ?? [];
  } catch {
    return [];
  }
}

export default async function SignInPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const { locale } = await params;
  const sp = await searchParams;
  setRequestLocale(locale);
  const t = await getTranslations("signIn");
  const accounts = await demoAccounts();
  const groups = [
    { key: "pets", accounts: accounts.filter((a) => PET_EMAILS.has(a.email)) },
    { key: "community", accounts: accounts.filter((a) => !PET_EMAILS.has(a.email)) },
  ].filter((g) => g.accounts.length > 0);
  return (
    <PublicPage locale={locale}>
      <div className="container-pg grid gap-6 py-8 md:py-12 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] lg:gap-10">
        <aside aria-labelledby="steps-h" className="h-fit rounded-card bg-sage p-6">
          <h2 id="steps-h" className="text-lg">{t("stepsTitle")}</h2>
          <ol className="mt-4 space-y-4">
            {(["one", "two", "three"] as const).map((k, i) => (
              <li key={k} className="flex gap-3">
                <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-primary font-display font-bold text-white">
                  {i + 1}
                </span>
                <div>
                  <p className="font-display font-semibold">{t(`steps.${k}.title`)}</p>
                  <p className="text-sm text-ink-2">{t(`steps.${k}.body`)}</p>
                </div>
              </li>
            ))}
          </ol>
        </aside>

        <div className="min-w-0 space-y-6">
          <div>
            <h1 className="text-3xl">{t("title")}</h1>
            <p className="mt-2 max-w-prose text-ink-2">{t("intro")}</p>
          </div>
          {sp.expired ? (
            <Notice tone="pending" live="polite">
              {t("expired")}
            </Notice>
          ) : null}
          {sp.signed_out ? (
            <Notice tone="success" live="polite">
              {t("signedOut")}
            </Notice>
          ) : null}
          <Card className="max-w-md">
            <SignInForm locale={locale} />
          </Card>
          <p className="text-sm text-ink-2">{t("noPublicSignup")}</p>

          {groups.length > 0 ? (
            <section aria-labelledby="demo-accounts" className="space-y-4 rounded-card border border-divider bg-surface p-5">
              <div>
                <h2 id="demo-accounts" className="text-lg">
                  {t("demoTitle")}
                </h2>
                <p className="mt-1 text-sm text-ink-2">
                  {t("demoIntro")} <Link href="/welcome">{t("howDemoWorks")}</Link>
                </p>
              </div>
              {groups.map((g) => (
                <div key={g.key} className="space-y-2">
                  <h3 className="text-base">{t(`demoGroups.${g.key}`)}</h3>
                  <ul className="grid gap-2 sm:grid-cols-2">
                    {g.accounts.map((a) => (
                      <li key={a.email}>
                        <form action={demoSignIn}>
                          <input type="hidden" name="email" value={a.email} />
                          <input type="hidden" name="locale" value={locale} />
                          <button
                            type="submit"
                            className="flex w-full items-center gap-3 rounded-control border border-control bg-surface p-3 text-left hover:bg-sage motion-safe:transition-colors motion-safe:duration-150"
                          >
                            <span aria-hidden className="grid size-9 shrink-0 place-items-center rounded-full bg-lavender font-display font-bold text-ink">
                              {a.name.replace(/^Dr /, "").charAt(0)}
                            </span>
                            <span className="min-w-0">
                              <span className="block font-display font-semibold">{t("demoSignInAs", { name: a.name })}</span>
                              <span className="block text-sm text-ink-2">{a.description}</span>
                            </span>
                          </button>
                        </form>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </section>
          ) : null}
        </div>
      </div>
    </PublicPage>
  );
}
