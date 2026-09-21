import { useEffect, useState } from "react";

/**
 * The entry gate.
 *
 * The counter tracks work that is actually happening — the health check and the
 * defect listing — rather than animating to 100 on a timer. If the API never
 * answers it says so and still lets you in, because a gate you cannot pass is
 * just a wall.
 */
export function Loader({
  ready,
  failed,
  onEnter,
}: {
  ready: number;
  failed: boolean;
  onEnter: () => void;
}) {
  const [shown, setShown] = useState(0);
  const [leaving, setLeaving] = useState(false);

  const target = Math.round(ready * 100);

  useEffect(() => {
    let frame = 0;
    const step = () => {
      setShown((current) => {
        if (current >= target) return target;
        return Math.min(target, current + Math.max(1, Math.ceil((target - current) / 8)));
      });
      frame = window.setTimeout(step, 28);
    };
    step();
    return () => window.clearTimeout(frame);
  }, [target]);

  const settled = target >= 100 || failed;

  const enter = () => {
    setLeaving(true);
    window.setTimeout(onEnter, 620);
  };

  return (
    <div
      data-testid="loader"
      aria-hidden={leaving}
      style={{
        opacity: leaving ? 0 : 1,
        transform: leaving ? "translateY(-2.5%)" : "none",
        transition: "opacity .6s cubic-bezier(.22,1,.36,1), transform .6s cubic-bezier(.22,1,.36,1)",
      }}
      className="fixed inset-0 z-100 flex flex-col justify-between bg-ink px-6 py-8 sm:px-12 sm:py-12"
    >
      <div className="flex items-baseline justify-between font-mono text-[11px] tracking-[0.2em] text-muted uppercase">
        <span>fixproof</span>
        <span>{failed ? "api unreachable" : "loading"}</span>
      </div>

      <div className="flex flex-col items-start gap-6">
        <span
          className="font-display font-semibold text-bone tabular-nums"
          style={{ fontSize: "clamp(4rem, 17vw, 13rem)", lineHeight: 0.84, letterSpacing: "-0.05em" }}
        >
          {String(shown).padStart(3, "0")}
        </span>
        <div className="h-px w-full bg-line">
          <div
            className="h-px bg-acid"
            style={{ width: `${shown}%`, transition: "width .3s cubic-bezier(.22,1,.36,1)" }}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-6">
        <p className="max-w-sm text-sm leading-relaxed text-muted">
          {failed
            ? "The backend is not answering. You can still read the site; the live section will stay empty."
            : "Checking the verifier image, the Docker engine and the fixture sets."}
        </p>
        <button
          type="button"
          onClick={enter}
          disabled={!settled}
          data-testid="enter"
          className="group flex h-14 items-center gap-4 border-b border-bone pb-1 font-display text-3xl font-medium tracking-tight text-bone transition disabled:cursor-not-allowed disabled:border-line disabled:text-muted sm:text-4xl"
        >
          enter
          <span className="transition-transform duration-300 group-enabled:group-hover:translate-x-2">
            &rarr;
          </span>
        </button>
      </div>
    </div>
  );
}
