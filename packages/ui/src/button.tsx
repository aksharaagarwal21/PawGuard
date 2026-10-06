import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { Slot } from "radix-ui";
import * as React from "react";

import { cn } from "./cn";

const buttonVariants = cva(
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-control px-4 py-2 font-display text-sm font-semibold no-underline transition-colors duration-150 ease-calm disabled:cursor-not-allowed disabled:opacity-60",
  {
    variants: {
      variant: {
        primary: "bg-primary text-white hover:bg-primary-hover",
        secondary: "border border-control bg-surface text-ink hover:bg-sage",
        quiet: "text-primary underline-offset-4 hover:bg-sage",
        danger: "bg-urgent text-white hover:brightness-90",
        urgent: "bg-urgent text-white hover:brightness-90 text-base px-5 min-h-12",
      },
      size: { md: "", sm: "min-h-11 px-3 text-xs", lg: "min-h-12 px-6 text-base" },
      block: { true: "w-full" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  /** Render the child element (e.g. a link) with button styling. */
  asChild?: boolean;
  /** Shows a spinner, keeps the width and marks the button busy. */
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, size, block, asChild, loading, children, disabled, ...props },
  ref,
) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      ref={ref}
      className={cn(buttonVariants({ variant, size, block }), className)}
      aria-busy={loading || undefined}
      disabled={asChild ? undefined : disabled || loading}
      {...props}
    >
      {asChild ? (
        children
      ) : (
        <>
          {loading ? <Loader2 aria-hidden className="size-4 animate-spin" /> : null}
          {children}
        </>
      )}
    </Comp>
  );
});

export { buttonVariants };
