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
  index,
  title,
  lead,
  children,
}: {
  id: string;
  index: string;
  title: string;
  lead?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24 border-t border-line px-6 py-20 sm:px-12 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <div className="flex flex-col gap-5 lg:flex-row lg:gap-16">
            <div className="lg:w-48 lg:shrink-0">
              <span className="font-mono text-[11px] tracking-[0.2em] text-acid uppercase">
                ({index})
              </span>
            </div>
            <div className="flex-1">
              <h2
                className="font-display font-semibold tracking-tight text-bone"
                style={{ fontSize: "clamp(2rem, 4.6vw, 3.6rem)", lineHeight: 1.02 }}
              >
                {title}
              </h2>
              {lead && (
                <p className="mt-5 max-w-2xl text-base leading-relaxed text-muted sm:text-lg">
                  {lead}
                </p>
              )}
            </div>
          </div>
        </Reveal>
        <div className="mt-12 lg:pl-64">{children}</div>
      </div>
    </section>
  );
}

export function Tag({
  children,
  tone = "muted",
}: {
  children: ReactNode;
  tone?: "muted" | "acid" | "reject";
}) {
  const tones = {
    muted: "border-line text-muted",
    acid: "border-acid/50 text-acid",
    reject: "border-reject/50 text-reject",
  };
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 font-mono text-[11px] ${tones[tone]}`}
    >
      {children}
    </span>
  );
}
