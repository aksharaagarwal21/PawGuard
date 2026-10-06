"use client";

import { useTranslations } from "next-intl";
import { useActionState, useEffect, useRef } from "react";

import { Button, Field, TextInput } from "@pawguard/ui";

import { signIn, type SignInState } from "@/lib/auth-actions";

export function SignInForm({ locale }: { locale: string }) {
  const t = useTranslations("signIn");
  const [state, action, pending] = useActionState<SignInState, FormData>(signIn, {});
  const errorRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (state.error) errorRef.current?.focus();
  }, [state]);
  return (
    <form action={action} noValidate className="space-y-5">
      <input type="hidden" name="locale" value={locale} />
      {state.error ? (
        <p ref={errorRef} tabIndex={-1} role="alert" className="rounded-control border-2 border-urgent p-3 font-semibold text-urgent">
          {t(`errors.${state.error}`)}
        </p>
      ) : null}
      <Field id="email" label={t("email")}>
        {(aria) => (
          <TextInput {...aria} name="email" type="email" autoComplete="username" required defaultValue={state.email ?? ""} />
        )}
      </Field>
      <Field id="password" label={t("password")}>
        {(aria) => <TextInput {...aria} name="password" type="password" autoComplete="current-password" required />}
      </Field>
      <Button type="submit" loading={pending} block>
        {t("submit")}
      </Button>
    </form>
  );
}
