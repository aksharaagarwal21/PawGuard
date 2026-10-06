/** Wordmark: a simple paw-in-shield glyph drawn for PawGuard (no third-party logo or partner marks). */
export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2 font-display text-lg font-extrabold tracking-tight text-ink">
      <svg aria-hidden viewBox="0 0 32 32" className="size-8 shrink-0">
        <path d="M16 2.5 4.5 7v8.2c0 7 4.9 12.4 11.5 14.3 6.6-1.9 11.5-7.3 11.5-14.3V7L16 2.5Z" fill="#205C4F" />
        <g fill="#F7F8F3">
          <ellipse cx="11.2" cy="12.2" rx="1.9" ry="2.4" />
          <ellipse cx="16" cy="10.4" rx="1.9" ry="2.4" />
          <ellipse cx="20.8" cy="12.2" rx="1.9" ry="2.4" />
          <path d="M16 14.6c-3.2 0-5.6 3.6-5.6 5.6 0 1.6 1.3 2.4 2.7 2.4 1.2 0 1.8-.6 2.9-.6s1.7.6 2.9.6c1.4 0 2.7-.8 2.7-2.4 0-2-2.4-5.6-5.6-5.6Z" />
        </g>
      </svg>
      {compact ? <span className="sr-only">PawGuard 360</span> : <span>PawGuard 360</span>}
    </span>
  );
}
