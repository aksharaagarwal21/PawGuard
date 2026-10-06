"use client";

import { LogOut } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";

import { Button, Dialog } from "@pawguard/ui";

import { signOut } from "@/lib/auth-actions";
import { getOps, wipeOfflineData } from "@/lib/offline/store";

async function hasFieldKit(): Promise<boolean> {
  if (!("indexedDB" in window)) return false;
  if (typeof indexedDB.databases !== "function") return true; // cannot tell; checking opens (and wipe removes) it
  return (await indexedDB.databases()).some((d) => d.name === "pawguard-field");
}

/** Sign out and remove this device's offline field data. Warns first if changes made offline were not sent. */
export function SignOutForm({ locale, className }: { locale: string; className: string }) {
  const tc = useTranslations("common");
  const t = useTranslations("field");
  const form = useRef<HTMLFormElement>(null);
  const [pending, setPending] = useState(0);

  async function finish() {
    await wipeOfflineData();
    const data = new FormData(form.current!);
    await signOut(data);
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (await hasFieldKit()) {
      const n = (await getOps()).length;
      if (n) {
        setPending(n);
        return;
      }
    }
    await finish();
  }

  return (
    <>
      <form ref={form} onSubmit={onSubmit}>
        <input type="hidden" name="locale" value={locale} />
        <button type="submit" className={className}>
          <LogOut aria-hidden className="size-4" />
          {tc("signOut")}
        </button>
      </form>
      <Dialog
        open={pending > 0}
        onOpenChange={(o) => !o && setPending(0)}
        title={t("signOutPendingTitle", { n: pending })}
        description={t("signOutPendingBody")}
        closeLabel={tc("close")}
        footer={
          <>
            <Button asChild variant="secondary">
              <a href={`/${locale}/field`}>{t("openKit")}</a>
            </Button>
            <Button variant="danger" onClick={finish}>
              {t("signOutAnyway")}
            </Button>
          </>
        }
      />
    </>
  );
}
