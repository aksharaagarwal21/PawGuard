"use client";

import { useTranslations } from "next-intl";
import { useSyncExternalStore } from "react";

import { StatusChip } from "@pawguard/ui";

function subscribe(cb: () => void) {
  window.addEventListener("online", cb);
  window.addEventListener("offline", cb);
  return () => {
    window.removeEventListener("online", cb);
    window.removeEventListener("offline", cb);
  };
}

/** Shows browser connectivity. "Online" only means the device has a network, not that data has synced. */
export function ConnectionStatus({ compact }: { compact?: boolean }) {
  const t = useTranslations("app");
  const online = useSyncExternalStore(
    subscribe,
    () => navigator.onLine,
    () => true,
  );
  return (
    <span role="status" aria-live="polite" className={compact ? "shrink-0" : undefined}>
      <StatusChip kind={online ? "online" : "offline"}>{online ? t("online") : t("offline")}</StatusChip>
    </span>
  );
}
