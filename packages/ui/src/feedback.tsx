import { AlertTriangle, CheckCircle2, Clock, Info, PencilLine, XCircle } from "lucide-react";
import * as React from "react";

import { cn } from "./cn";

type Tone = "info" | "pending" | "urgent" | "success" | "neutral";

const toneStyles: Record<Tone, string> = {
  info: "bg-sky",
  pending: "bg-sand",
  urgent: "bg-urgent-soft border-l-4 border-urgent",
  success: "bg-sage",
  neutral: "bg-surface border border-divider",
};

const toneIcon: Record<Tone, React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>> = {
  info: Info,
  pending: Clock,
  urgent: AlertTriangle,
  success: CheckCircle2,
  neutral: Info,
};

export interface NoticeProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  tone?: Tone;
  title?: React.ReactNode;
  /** Use "alert" only for problems the user must act on now. */
  live?: "polite" | "alert";
}

/** A block message. Tone is conveyed with an icon and text, never colour alone. */
export function Notice({ tone = "info", title, live, className, children, ...props }: NoticeProps) {
  const Icon = toneIcon[tone];
  return (
    <div
      role={live === "alert" ? "alert" : live === "polite" ? "status" : undefined}
      className={cn("flex gap-3 rounded-card p-4 text-ink", toneStyles[tone], className)}
      {...props}
    >
      <Icon aria-hidden className={cn("mt-0.5 size-5 shrink-0", tone === "urgent" ? "text-urgent" : "text-primary")} />
      <div className="min-w-0 space-y-1">
        {title ? <p className="font-display font-semibold">{title}</p> : null}
        <div className="text-ink [&_p]:mt-1">{children}</div>
      </div>
    </div>
  );
}

export type ChipKind =
  | "verified"
  | "submitted"
  | "needs_correction"
  | "rejected"
  | "draft"
  | "superseded"
  | "provisional"
  | "reviewed"
  | "disputed"
  | "neutral"
  | "offline"
  | "online"
  | "demo";

const chipStyles: Record<ChipKind, { cls: string; Icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }> | null }> = {
  verified: { cls: "bg-sage text-ink", Icon: CheckCircle2 },
  reviewed: { cls: "bg-sage text-ink", Icon: CheckCircle2 },
  submitted: { cls: "bg-sand text-ink", Icon: Clock },
  provisional: { cls: "bg-sand text-ink", Icon: Clock },
  needs_correction: { cls: "bg-sand text-ink", Icon: PencilLine },
  disputed: { cls: "bg-sand text-ink", Icon: AlertTriangle },
  rejected: { cls: "border border-urgent text-urgent bg-surface", Icon: XCircle },
  draft: { cls: "border border-control text-ink-2 bg-surface", Icon: null },
  superseded: { cls: "border border-control text-ink-2 bg-surface", Icon: null },
  neutral: { cls: "border border-control text-ink bg-surface", Icon: null },
  offline: { cls: "bg-sand text-ink", Icon: AlertTriangle },
  online: { cls: "bg-sage text-ink", Icon: null },
  demo: { cls: "bg-lavender text-ink", Icon: null },
};

export interface StatusChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  kind: ChipKind;
}

/** Status label: text + optional icon. Callers pass the reviewed wording from DESIGN_SYSTEM.md. */
export function StatusChip({ kind, className, children, ...props }: StatusChipProps) {
  const { cls, Icon } = chipStyles[kind];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-display text-xs font-semibold whitespace-nowrap",
        cls,
        className,
      )}
      {...props}
    >
      {Icon ? <Icon aria-hidden className="size-3.5" /> : null}
      {children}
    </span>
  );
}

export interface EmptyStateProps {
  title: React.ReactNode;
  children?: React.ReactNode;
  action?: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
}

export function EmptyState({ title, children, action, icon, className }: EmptyStateProps) {
  return (
    <div className={cn("rounded-card border border-dashed border-control bg-surface p-6 text-center", className)}>
      {icon ? <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-full bg-sage text-primary">{icon}</div> : null}
      <p className="font-display text-lg font-semibold">{title}</p>
      {children ? <div className="mx-auto mt-2 max-w-prose text-ink-2">{children}</div> : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-md bg-divider/60", className)} />;
}

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-card border border-divider bg-surface p-4 shadow-card sm:p-6", className)}
      {...props}
    />
  );
}

export function VisuallyHidden({ children }: { children: React.ReactNode }) {
  return <span className="sr-only">{children}</span>;
}
