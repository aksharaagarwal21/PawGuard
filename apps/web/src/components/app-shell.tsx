import {
  Activity,
  Backpack,
  Bell,
  BookOpen,
  CalendarRange,
  Camera,
  ClipboardCheck,
  Compass,
  Dog,
  FileSpreadsheet,
  FlaskConical,
  House,
  ListChecks,
  Map,
  Menu,
  MessageCircleQuestion,
  PawPrint,
  Send,
  Stethoscope,
} from "lucide-react";
import { getTranslations } from "next-intl/server";

import { StatusChip } from "@pawguard/ui";

import { Link } from "@/i18n/navigation";
import { TranslationNotice } from "@/components/public-shell";
import { SignOutForm } from "@/components/sign-out-form";
import { chooseOrganisation } from "@/lib/auth-actions";
import { visibleNav, type NavItem } from "@/lib/nav";
import { serverApi, type Me, type MembershipInfo } from "@/lib/session";

import { ConnectionStatus } from "./connection-status";
import { LanguageSwitcher } from "./language-switcher";
import { NavLink } from "./nav-link";
import { DemoBanner } from "./public-shell";
import { Wordmark } from "./wordmark";

const ICONS: Record<NavItem["icon"], React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>> = {
  today: House,
  pets: Dog,
  reminders: Bell,
  notifications: Send,
  assistant: MessageCircleQuestion,
  clinic: Stethoscope,
  animals: PawPrint,
  capture: Camera,
  review: ClipboardCheck,
  tasks: ListChecks,
  map: Map,
  imports: FileSpreadsheet,
  field: Backpack,
  campaigns: CalendarRange,
  modelEvidence: FlaskConical,
  system: Activity,
};

export async function AppShell({
  me,
  active,
  locale,
  children,
}: {
  me: Me;
  active: MembershipInfo;
  locale: string;
  children: React.ReactNode;
}) {
  const t = await getTranslations("nav");
  const ta = await getTranslations("app");
  const tr = await getTranslations("roles");
  const items = visibleNav(active.capabilities, active.professional_scopes, active.org_type);
  const mobileItems = items.filter((i) => i.mobile);
  // Pet owners: count of reminders showing today, for the bell.
  let reminderCount = 0;
  if (active.capabilities.includes("pet.own")) {
    const { data } = await (await serverApi(active.org_id)).GET("/api/v1/my/reminders").catch(() => ({ data: undefined }));
    reminderCount = data?.length ?? 0;
  }
  // "Show tour again" (Help): owners on My pets, clinic staff on the clinic dashboard.
  const tourHref = active.capabilities.includes("pet.own")
    ? "/app/pets?tour=1"
    : active.org_type === "veterinary_service" && active.capabilities.includes("animal.read")
      ? "/app/clinic?tour=1"
      : null;
  const bell = active.capabilities.includes("pet.own") ? (
    <Link
      href="/app/reminders"
      data-tour="bell"
      className="relative inline-flex min-h-11 min-w-11 items-center justify-center rounded-control text-ink no-underline hover:bg-sage"
      aria-label={reminderCount ? t("remindersBellCount", { count: reminderCount }) : t("reminders")}
    >
      <Bell aria-hidden className="size-5" />
      {reminderCount ? (
        <span aria-hidden className="absolute top-1 right-0.5 min-w-5 rounded-full bg-urgent px-1 text-center text-xs font-bold text-white">
          {reminderCount}
        </span>
      ) : null}
    </Link>
  ) : null;

  const orgSwitcher =
    me.memberships.length > 1 ? (
      <form action={chooseOrganisation} className="space-y-2">
        <input type="hidden" name="locale" value={locale} />
        <label className="block">
          <span className="block text-xs font-semibold text-ink-2">{t("organisation")}</span>
          <select
            name="org_id"
            defaultValue={active.org_id}
            className="mt-1 min-h-11 w-full rounded-control border border-control bg-surface px-2 text-sm"
          >
            {me.memberships.map((m) => (
              <option key={m.org_id} value={m.org_id}>
                {m.org_name}
              </option>
            ))}
          </select>
        </label>
        <button
          type="submit"
          className="min-h-11 w-full rounded-control border border-control bg-surface px-3 text-sm font-semibold hover:bg-sage"
        >
          {t("switchOrganisation")}
        </button>
      </form>
    ) : (
      <div>
        <span className="block text-xs font-semibold text-ink-2">{t("organisation")}</span>
        <span className="mt-1 block font-display text-sm font-semibold">{active.org_name}</span>
      </div>
    );

  return (
    <div className="min-h-dvh md:grid md:grid-cols-[17rem_1fr]">
      <aside className="hidden border-r border-divider bg-surface md:flex md:min-h-dvh md:flex-col">
        <div className="flex items-center justify-between gap-2 p-5">
          <Link href="/app" className="no-underline">
            <Wordmark />
          </Link>
          {bell}
        </div>
        <div className="space-y-3 border-y border-divider px-5 py-4">
          {orgSwitcher}
          <div className="flex flex-wrap gap-2">
            <StatusChip kind="neutral">{tr(active.role)}</StatusChip>
            {active.org_is_demo ? <StatusChip kind="demo">{ta("demoOrg")}</StatusChip> : null}
          </div>
        </div>
        <nav aria-label={t("appNavigation")} className="flex-1 p-3">
          <ul className="space-y-1">
            {items.map((i) => {
              const Icon = ICONS[i.icon];
              return (
                <li key={i.key}>
                  <NavLink href={i.href} exact={i.href === "/app"}>
                    <Icon aria-hidden className="size-5" />
                    {t(i.labelKey)}
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="space-y-3 border-t border-divider p-5">
          <div>
            <p className="text-xs font-semibold text-ink-2">{t("helpMenu")}</p>
            <Link href="/guide" className="flex min-h-11 items-center gap-2 text-sm font-semibold">
              <BookOpen aria-hidden className="size-4" />
              {t("howToUse")}
            </Link>
            {tourHref ? (
              <Link href={tourHref} className="flex min-h-11 items-center gap-2 text-sm font-semibold">
                <Compass aria-hidden className="size-4" />
                {t("showTour")}
              </Link>
            ) : null}
          </div>
          <div>
            <ConnectionStatus />
          </div>
          <LanguageSwitcher />
          <SignOutForm locale={locale} className="inline-flex min-h-11 items-center gap-2 rounded-control px-2 text-sm font-semibold text-ink hover:bg-sage" />
        </div>
      </aside>

      <div className="flex min-h-dvh flex-col pb-20 md:pb-0">
        <DemoBanner />
        <TranslationNotice locale={locale} />
        <header className="flex items-center gap-3 border-b border-divider bg-surface px-4 py-2 md:hidden">
          <Link href="/app" className="no-underline">
            <Wordmark compact />
          </Link>
          <span className="min-w-0 flex-1 truncate font-display text-sm font-semibold">{active.org_name}</span>
          {bell}
          <ConnectionStatus compact />
        </header>
        <main id="main" tabIndex={-1} className="flex-1 outline-none">
          {children}
        </main>
      </div>

      <nav aria-label={t("appNavigation")} className="fixed inset-x-0 bottom-0 z-30 border-t border-divider bg-surface md:hidden">
        <ul className="grid" style={{ gridTemplateColumns: `repeat(${mobileItems.length + 1}, minmax(0, 1fr))` }}>
          {mobileItems.map((i) => {
            const Icon = ICONS[i.icon];
            return (
              <li key={i.key}>
                <NavLink href={i.href} exact={i.href === "/app"} mobile>
                  <Icon aria-hidden className="size-5" />
                  {t(i.labelKey)}
                </NavLink>
              </li>
            );
          })}
          <li>
            <NavLink href="/app/more" mobile>
              <Menu aria-hidden className="size-5" />
              {t("more")}
            </NavLink>
          </li>
        </ul>
      </nav>
    </div>
  );
}
