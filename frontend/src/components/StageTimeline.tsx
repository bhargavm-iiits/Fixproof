import { STAGES } from "../api";

export type StageState = "pending" | "running" | "done";

export function StageTimeline({
  states,
  timings,
}: {
  states: Record<string, StageState>;
  timings: Record<string, number>;
}) {
  return (
    <ol className="flex flex-wrap items-stretch gap-2">
      {STAGES.map((stage) => {
        const state = states[stage] ?? "pending";
        const tone =
          state === "done"
            ? "border-pass/40 bg-pass/10 text-pass"
            : state === "running"
              ? "border-accent/60 bg-accent/10 text-accent animate-pulse"
              : "border-edge bg-black/20 text-muted/60";
        return (
          <li
            key={stage}
            data-stage={stage}
            data-state={state}
            className={`min-w-[104px] flex-1 rounded-lg border px-3 py-2 ${tone}`}
          >
            <div className="text-xs font-semibold">{stage}</div>
            <div className="mt-0.5 text-[11px] tabular-nums opacity-80">
              {timings[stage] !== undefined
                ? `${timings[stage].toFixed(0)} ms`
                : state === "running"
                  ? "running"
                  : "—"}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
