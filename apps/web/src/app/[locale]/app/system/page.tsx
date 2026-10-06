import { CheckCircle2, XCircle } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Card, Notice, StatusChip, type ChipKind } from "@pawguard/ui";

import { activeMembership, getMe, serverApi } from "@/lib/session";

const STATUS_CHIP: Record<string, ChipKind> = {
  available: "verified",
  unavailable: "rejected",
  preview_only: "submitted",
  not_configured: "neutral",
  research_only: "submitted",
};

export default async function SystemPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("system");
  const te = await getTranslations("errors");
  const result = await getMe();
  if (result.state !== "ok") return null;
  const active = await activeMembership(result.me);
  const api = await serverApi(active?.org_id);
  const { data, response } = await api.GET("/api/v1/system/providers");
  if (response.status === 403) {
    return (
      <div className="px-4 py-6 md:px-8">
        <Notice tone="urgent" title={te("forbiddenTitle")}>
          {te("forbiddenBody")}
        </Notice>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="px-4 py-6 md:px-8">
        <Notice tone="urgent" title={te("unavailableTitle")}>
          {te("unavailableBody")}
        </Notice>
      </div>
    );
  }
  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-6 md:px-8 md:py-10">
      <div>
        <h1 className="text-2xl">{t("title")}</h1>
        <p className="mt-1 text-ink-2">{t("intro")}</p>
      </div>
      <Card>
        <h2 className="text-lg">{t("components")}</h2>
        <ul className="mt-3 divide-y divide-divider">
          {Object.entries(data.components).map(([name, info]) => {
            const ok = Boolean((info as { ok?: boolean }).ok);
            return (
              <li key={name} className="flex items-center justify-between gap-4 py-2.5">
                <span className="font-mono text-sm">{name}</span>
                <span className="inline-flex items-center gap-1.5 text-sm font-semibold">
                  {ok ? (
                    <CheckCircle2 aria-hidden className="size-4 text-primary" />
                  ) : (
                    <XCircle aria-hidden className="size-4 text-urgent" />
                  )}
                  {ok ? t("ok") : t("notOk")}
                </span>
              </li>
            );
          })}
        </ul>
      </Card>
      <Card>
        <h2 className="text-lg">{t("integrations")}</h2>
        <ul className="mt-3 divide-y divide-divider">
          {data.capabilities.map((c) => (
            <li key={c.key} className="grid gap-1 py-3 sm:grid-cols-[12rem_10rem_1fr] sm:items-center">
              <span className="font-mono text-sm">{c.key}</span>
              <span>
                <StatusChip kind={STATUS_CHIP[c.status] ?? "neutral"}>
                  {t.has(`status.${c.status}`) ? t(`status.${c.status}`) : c.status}
                </StatusChip>
              </span>
              <span className="text-sm text-ink-2">{c.detail}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
