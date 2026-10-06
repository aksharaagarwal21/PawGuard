import { createApiClient } from "@pawguard/api-client";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Card, Notice } from "@pawguard/ui";

import { PublicPage } from "@/components/public-shell";
import { demoSignIn } from "@/lib/auth-actions";
import { serverEnv } from "@/lib/server-env";

import { SignInForm } from "./sign-in-form";

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
  return (
    <PublicPage locale={locale}>
      <div className="container-pg grid gap-8 py-10 lg:grid-cols-[minmax(0,28rem)_1fr]">
        <div>
          <h1 className="text-3xl">{t("title")}</h1>
          <p className="mt-3 text-ink-2">{t("intro")}</p>
          {sp.expired ? (
            <Notice tone="pending" className="mt-4" live="polite">
              {t("expired")}
            </Notice>
          ) : null}
          {sp.signed_out ? (
            <Notice tone="success" className="mt-4" live="polite">
              {t("signedOut")}
            </Notice>
          ) : null}
          <Card className="mt-6">
            <SignInForm locale={locale} />
          </Card>
          <p className="mt-4 text-sm text-ink-2">{t("noPublicSignup")}</p>
        </div>
        {accounts.length > 0 ? (
          <section aria-labelledby="demo-accounts" className="rounded-card bg-lavender p-6">
            <h2 id="demo-accounts" className="text-lg">
              {t("demoTitle")}
            </h2>
            <p className="mt-1 text-sm">{t("demoIntro")}</p>
            <ul className="mt-4 grid gap-2 sm:grid-cols-2">
              {accounts.map((a) => (
                <li key={a.email}>
                  <form action={demoSignIn}>
                    <input type="hidden" name="email" value={a.email} />
                    <input type="hidden" name="locale" value={locale} />
                    <button
                      type="submit"
                      className="w-full rounded-control border border-control bg-surface p-3 text-left hover:bg-sage"
                    >
                      <span className="block font-display font-semibold">{t("demoSignInAs", { name: a.name })}</span>
                      <span className="block text-sm text-ink-2">{a.description}</span>
                    </button>
                  </form>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </PublicPage>
  );
}
