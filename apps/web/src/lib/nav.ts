/**
 * Authenticated navigation. Items appear only when (a) the module exists in this release and (b) the user's
 * membership has one of the listed capabilities (and, for review, the approved professional scope). The API
 * enforces the same rules on every request regardless of what the menu shows.
 */
export type NavIcon =
  | "today"
  | "pets"
  | "reminders"
  | "notifications"
  | "assistant"
  | "lost"
  | "clinic"
  | "animals"
  | "capture"
  | "review"
  | "tasks"
  | "map"
  | "campaigns"
  | "field"
  | "imports"
  | "modelEvidence"
  | "system";

/** Capabilities that make someone organisation staff (pet owners hold only `pet.own` and `media.upload`). */
export const STAFF_CAPS = ["animal.read", "task.work", "task.manage", "vaccination.submit", "member.manage", "system.view"];

export type NavItem = {
  key: string;
  href: string;
  labelKey: string;
  icon: NavIcon;
  anyOf?: string[];
  needsScope?: string;
  /** Only in these organisation types (e.g. the clinic dashboard in veterinary services). */
  orgTypes?: string[];
  mobile: boolean;
};

export const NAV_ITEMS: NavItem[] = [
  { key: "today", href: "/app", labelKey: "today", icon: "today", anyOf: STAFF_CAPS, mobile: true },
  { key: "pets", href: "/app/pets", labelKey: "pets", icon: "pets", anyOf: ["pet.own"], mobile: true },
  { key: "reminders", href: "/app/reminders", labelKey: "reminders", icon: "reminders", anyOf: ["pet.own"], mobile: true },
  { key: "lost", href: "/app/lost", labelKey: "lost", icon: "lost", anyOf: ["pet.own"], mobile: false },
  { key: "assistant", href: "/app/assistant", labelKey: "assistant", icon: "assistant", anyOf: ["pet.own"], mobile: false },
  { key: "notifications", href: "/app/notifications", labelKey: "notifications", icon: "notifications", anyOf: ["pet.own"], mobile: false },
  {
    key: "clinic",
    href: "/app/clinic",
    labelKey: "clinic",
    icon: "clinic",
    anyOf: ["animal.read"],
    orgTypes: ["veterinary_service"],
    mobile: true,
  },
  { key: "animals", href: "/app/animals", labelKey: "animals", icon: "animals", anyOf: ["animal.read"], mobile: true },
  { key: "capture", href: "/app/capture", labelKey: "capture", icon: "capture", anyOf: ["observation.write"], mobile: true },
  {
    key: "review",
    href: "/app/review",
    labelKey: "review",
    icon: "review",
    anyOf: ["vaccination.review"],
    needsScope: "veterinary_review",
    mobile: false,
  },
  { key: "tasks", href: "/app/tasks", labelKey: "tasks", icon: "tasks", anyOf: ["task.work", "task.manage"], mobile: false },
  { key: "map", href: "/app/map", labelKey: "map", icon: "map", anyOf: ["animal.read"], mobile: false },
  { key: "campaigns", href: "/app/campaigns", labelKey: "campaigns", icon: "campaigns", anyOf: ["campaign.manage"], mobile: false },
  { key: "field", href: "/field", labelKey: "field", icon: "field", anyOf: ["task.work"], mobile: false },
  { key: "imports", href: "/app/imports", labelKey: "imports", icon: "imports", anyOf: ["data.import"], mobile: false },
  { key: "modelEvidence", href: "/app/model-evidence", labelKey: "modelEvidence", icon: "modelEvidence", anyOf: ["animal.read"], mobile: false },
  { key: "system", href: "/app/system", labelKey: "system", icon: "system", anyOf: ["system.view"], mobile: false },
];

export function visibleNav(
  capabilities: readonly string[],
  scopes: readonly string[] = [],
  orgType?: string,
): NavItem[] {
  return NAV_ITEMS.filter(
    (i) =>
      (!i.anyOf || i.anyOf.some((c) => capabilities.includes(c))) &&
      (!i.needsScope || scopes.includes(i.needsScope)) &&
      (!i.orgTypes || (orgType !== undefined && i.orgTypes.includes(orgType))),
  );
}
