import type { ReactNode } from "react";
import { useReveal } from "../lib/motion";

export function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  const { ref, shown } = useReveal<HTMLDivElement>();
  return (
    <div
      ref={ref}
      data-shown={shown}
      className={`reveal ${className}`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  );
}

export function Section({
  id,
  title,
  lead,
  children,
}: {
  id: string;
  title: string;
  lead?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-20 border-t border-line px-6 py-16 sm:px-10 sm:py-20">
      <div className="mx-auto max-w-4xl">
        <Reveal>
          <h2
            className="font-display font-semibold tracking-tight text-bone"
            style={{ fontSize: "clamp(1.75rem, 3.6vw, 2.6rem)", lineHeight: 1.12 }}
          >
            {title}
          </h2>
          {lead && <p className="mt-4 max-w-2xl text-body">{lead}</p>}
        </Reveal>
        <div className="mt-10">{children}</div>
      </div>
    </section>
  );
}

const TONES = {
  good: "border-acid/50 bg-acid/10 text-acid",
  bad: "border-reject/50 bg-reject/10 text-reject",
  warn: "border-line bg-white/5 text-body",
  plain: "border-line text-muted",
};

export function Tag({
  children,
  tone = "plain",
}: {
  children: ReactNode;
  tone?: keyof typeof TONES;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[13px] ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

/** The technical name, for anyone who wants it, never in the way of anyone who doesn't. */
export function TechName({ children }: { children: ReactNode }) {
  return <code className="font-mono text-[12px] text-muted">{children}</code>;
}
