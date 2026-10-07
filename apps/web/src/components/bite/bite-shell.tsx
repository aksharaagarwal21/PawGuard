import { getTranslations } from "next-intl/server";

import { LanguageSwitcher } from "@/components/language-switcher";
import { Wordmark } from "@/components/wordmark";
import { serverEnv } from "@/lib/server-env";

/** Minimal frame for bite pages: a slim bar with the language switch, then the page — so first aid is the first
 *  content on a phone, usable with one hand. The demo note comes after the content. */
export async function BiteShell({ children }: { children: React.ReactNode }) {
  const t = await getTranslations("common");
  return (
    <>
      <header className="border-b border-divider bg-canvas">
        <div className="container-pg flex min-h-12 items-center justify-between gap-3 py-1">
          <Wordmark compact />
          <LanguageSwitcher />
        </div>
      </header>
      <main id="main" tabIndex={-1} className="outline-none">
        <div className="container-pg max-w-2xl space-y-5 py-5">{children}</div>
      </main>
      {serverEnv().demoMode ? (
        <footer className="bg-lavender">
          <p className="container-pg py-2 text-sm font-semibold">{t("demoBanner")}</p>
        </footer>
      ) : null}
    </>
  );
}
