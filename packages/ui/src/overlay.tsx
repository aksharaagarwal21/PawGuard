"use client";

import { X } from "lucide-react";
import { Dialog as RDialog, Toast as RToast } from "radix-ui";
import * as React from "react";

import { cn } from "./cn";

export interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  closeLabel: string;
}

/** Modal dialog (Radix): focus trap, Escape to close, focus returns to the trigger. */
export function Dialog({ open, onOpenChange, title, description, children, footer, closeLabel }: DialogProps) {
  return (
    <RDialog.Root open={open} onOpenChange={onOpenChange}>
      <RDialog.Portal>
        <RDialog.Overlay className="fixed inset-0 z-40 bg-ink/40" />
        <RDialog.Content className="fixed top-1/2 left-1/2 z-50 max-h-[90vh] w-[calc(100vw-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-card bg-surface p-6 shadow-lg">
          <div className="flex items-start justify-between gap-4">
            <RDialog.Title className="font-display text-xl font-bold">{title}</RDialog.Title>
            <RDialog.Close className="-mt-1 -mr-2 inline-flex size-11 items-center justify-center rounded-md text-ink-2 hover:bg-sage">
              <X aria-hidden className="size-5" />
              <span className="sr-only">{closeLabel}</span>
            </RDialog.Close>
          </div>
          {description ? <RDialog.Description className="mt-2 text-ink-2">{description}</RDialog.Description> : null}
          {children ? <div className="mt-4">{children}</div> : null}
          {footer ? <div className="mt-6 flex flex-wrap justify-end gap-3">{footer}</div> : null}
        </RDialog.Content>
      </RDialog.Portal>
    </RDialog.Root>
  );
}

type ToastTone = "success" | "info" | "error";
interface ToastItem {
  id: number;
  title: string;
  body?: string;
  tone: ToastTone;
}
const ToastCtx = React.createContext<(t: Omit<ToastItem, "id">) => void>(() => {});

/** Toasts confirm completed actions; they are never the only place important information appears. */
export function ToastProvider({ children, closeLabel }: { children: React.ReactNode; closeLabel: string }) {
  const [items, setItems] = React.useState<ToastItem[]>([]);
  const push = React.useCallback((t: Omit<ToastItem, "id">) => {
    setItems((prev) => [...prev, { ...t, id: Date.now() + Math.random() }]);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      <RToast.Provider duration={6000}>
        {children}
        {items.map((t) => (
          <RToast.Root
            key={t.id}
            type={t.tone === "error" ? "foreground" : "background"}
            onOpenChange={(open) => !open && setItems((prev) => prev.filter((x) => x.id !== t.id))}
            className={cn(
              "flex items-start gap-3 rounded-card border bg-surface p-4 shadow-lg",
              t.tone === "error" ? "border-urgent" : "border-divider",
            )}
          >
            <div className="min-w-0 flex-1">
              <RToast.Title className="font-display font-semibold">{t.title}</RToast.Title>
              {t.body ? <RToast.Description className="text-sm text-ink-2">{t.body}</RToast.Description> : null}
            </div>
            <RToast.Close className="inline-flex size-11 items-center justify-center rounded-md hover:bg-sage">
              <X aria-hidden className="size-4" />
              <span className="sr-only">{closeLabel}</span>
            </RToast.Close>
          </RToast.Root>
        ))}
        <RToast.Viewport className="fixed right-4 bottom-20 z-50 flex w-[calc(100vw-2rem)] max-w-sm flex-col gap-2 outline-none md:bottom-4" />
      </RToast.Provider>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return React.useContext(ToastCtx);
}
