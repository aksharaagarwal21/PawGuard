import { ArrowLeft } from "lucide-react";

import { Link } from "@/i18n/navigation";

export function PageHeader({
  title,
  intro,
  back,
  actions,
  children,
}: {
  title: React.ReactNode;
  intro?: React.ReactNode;
  back?: { href: string; label: string };
  actions?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      {back ? (
        <Link href={back.href} className="inline-flex min-h-11 items-center gap-1.5 text-sm font-semibold no-underline">
          <ArrowLeft aria-hidden className="size-4" />
          {back.label}
        </Link>
      ) : null}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl">{title}</h1>
          {intro ? <p className="mt-1 max-w-prose text-ink-2">{intro}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
      </div>
      {children}
    </div>
  );
}

export function PageBody({ children, wide }: { children: React.ReactNode; wide?: boolean }) {
  return <div className={`mx-auto space-y-6 px-4 py-6 md:px-8 md:py-8 ${wide ? "max-w-6xl" : "max-w-4xl"}`}>{children}</div>;
}
