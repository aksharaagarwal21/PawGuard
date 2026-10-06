"use client";

import { Link, usePathname } from "@/i18n/navigation";

export function NavLink({
  href,
  exact,
  mobile,
  children,
}: {
  href: string;
  exact?: boolean;
  mobile?: boolean;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const current = exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
  const base = mobile
    ? "flex min-h-14 flex-col items-center justify-center gap-0.5 text-xs font-semibold no-underline"
    : "flex min-h-11 items-center gap-3 rounded-control px-3 font-display text-sm font-semibold no-underline";
  return (
    <Link
      href={href}
      aria-current={current ? "page" : undefined}
      className={`${base} ${current ? "bg-sage text-primary" : "text-ink hover:bg-sage"}`}
    >
      {children}
    </Link>
  );
}
