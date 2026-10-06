import * as React from "react";

import { cn } from "./cn";

const controlBase =
  "block w-full rounded-control border border-control bg-surface px-3 py-2.5 text-base text-ink placeholder:text-ink-2/80 disabled:bg-canvas disabled:text-ink-2 aria-[invalid=true]:border-urgent aria-[invalid=true]:border-2";

export interface FieldProps {
  id: string;
  label: React.ReactNode;
  hint?: React.ReactNode;
  error?: React.ReactNode;
  /** Shown after the label: "(optional)" or "(required)" wording comes from the caller's translations. */
  marker?: React.ReactNode;
  children: (aria: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => React.ReactNode;
  className?: string;
}

/** Label + hint + error wiring. Errors are text (with an icon-free prefix) and linked by aria-describedby. */
export function Field({ id, label, hint, error, marker, children, className }: FieldProps) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={id} className="block font-display text-sm font-semibold text-ink">
        {label} {marker ? <span className="font-body font-normal text-ink-2">{marker}</span> : null}
      </label>
      {hint ? (
        <p id={hintId} className="text-sm text-ink-2">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-sm font-semibold text-urgent">
          {error}
        </p>
      ) : null}
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
    </div>
  );
}

export const TextInput = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function TextInput({ className, ...props }, ref) {
    return <input ref={ref} className={cn(controlBase, "min-h-11", className)} {...props} />;
  },
);

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...props }, ref) {
    return <textarea ref={ref} className={cn(controlBase, "min-h-24", className)} {...props} />;
  },
);

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, children, ...props }, ref) {
    return (
      <select ref={ref} className={cn(controlBase, "min-h-11 pr-8", className)} {...props}>
        {children}
      </select>
    );
  },
);

export interface ErrorSummaryProps {
  title: React.ReactNode;
  errors: { fieldId: string; message: React.ReactNode }[];
}

/** Focus moves here after a failed submit; each item links to its field. */
export const ErrorSummary = React.forwardRef<HTMLDivElement, ErrorSummaryProps>(function ErrorSummary(
  { title, errors },
  ref,
) {
  if (errors.length === 0) return null;
  return (
    <div ref={ref} tabIndex={-1} role="alert" className="rounded-card border-2 border-urgent bg-surface p-4">
      <p className="font-display font-semibold text-urgent">{title}</p>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        {errors.map((e) => (
          <li key={e.fieldId}>
            <a href={`#${e.fieldId}`} className="font-semibold text-urgent underline">
              {e.message}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
});

export interface RadioOption {
  value: string;
  label: React.ReactNode;
  hint?: React.ReactNode;
}

export interface RadioGroupProps {
  name: string;
  legend: React.ReactNode;
  options: RadioOption[];
  value?: string;
  onChange?: (value: string) => void;
  error?: React.ReactNode;
  inline?: boolean;
}

export function RadioGroup({ name, legend, options, value, onChange, error, inline }: RadioGroupProps) {
  const errorId = error ? `${name}-error` : undefined;
  return (
    <fieldset aria-describedby={errorId} className="space-y-2">
      <legend className="font-display text-sm font-semibold">{legend}</legend>
      {error ? (
        <p id={errorId} className="text-sm font-semibold text-urgent">
          {error}
        </p>
      ) : null}
      <div className={cn(inline ? "flex flex-wrap gap-2" : "space-y-2")}>
        {options.map((o) => {
          const id = `${name}-${o.value}`;
          return (
            <label
              key={o.value}
              htmlFor={id}
              className="flex min-h-11 cursor-pointer items-start gap-3 rounded-control border border-control bg-surface px-3 py-2.5 has-[:checked]:border-2 has-[:checked]:border-primary has-[:checked]:bg-sage"
            >
              <input
                id={id}
                type="radio"
                name={name}
                value={o.value}
                checked={value === undefined ? undefined : value === o.value}
                onChange={() => onChange?.(o.value)}
                className="mt-1 size-4 accent-primary"
              />
              <span>
                <span className="block">{o.label}</span>
                {o.hint ? <span className="block text-sm text-ink-2">{o.hint}</span> : null}
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
