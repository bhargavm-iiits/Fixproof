import type { ReactNode } from "react";

export function Panel({
  title,
  subtitle,
  children,
  right,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  right?: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-edge bg-panel/70 shadow-lg shadow-black/20">
      {(title || right) && (
        <header className="flex items-start justify-between gap-4 border-b border-edge px-5 py-3">
          <div>
            {title && <h2 className="text-sm font-semibold tracking-wide">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {right}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

const TONES: Record<string, string> = {
  pass: "bg-pass/15 text-pass border-pass/40",
  fail: "bg-fail/15 text-fail border-fail/40",
  warn: "bg-warn/15 text-warn border-warn/40",
  info: "bg-accent/15 text-accent border-accent/40",
  muted: "bg-white/5 text-muted border-edge",
};

export function Badge({
  tone = "muted",
  children,
  title,
}: {
  tone?: keyof typeof TONES | string;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${
        TONES[tone] ?? TONES.muted
      }`}
    >
      {children}
    </span>
  );
}

export const DECISION_TONE: Record<string, string> = {
  FIX_VERIFIED: "pass",
  NO_VERIFIED_FIX: "warn",
  ALL_GATED: "warn",
  TIMEOUT: "fail",
  ERROR: "fail",
};

export function Stat({
  label,
  value,
  hint,
  tone = "muted",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: string;
}) {
  const accent =
    tone === "pass" ? "text-pass" : tone === "fail" ? "text-fail" : tone === "warn" ? "text-warn" : "";
  return (
    <div className="rounded-lg border border-edge bg-black/20 px-4 py-3">
      <div className="text-[11px] uppercase tracking-wider text-muted">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${accent}`}>{value}</div>
      {hint && <div className="mt-1 text-[11px] leading-snug text-muted">{hint}</div>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-lg border border-dashed border-edge px-4 py-6 text-center text-sm text-muted">
      {children}
    </p>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted" role="status">
      <span className="h-3 w-3 animate-spin rounded-full border-2 border-muted border-t-transparent" />
      {label}
    </div>
  );
}
