import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Section } from "../components/Section";

const BUDGET: Record<string, string> = {
  prepare: "—",
  baseline: "VERIFIER_TIMEOUT_SECONDS",
  retrieve: "MAX_RUN_SECONDS",
  propose: "MODEL_TIMEOUT_SECONDS",
  gate: "MAX_RUN_SECONDS",
  verify: "VERIFIER_TIMEOUT_SECONDS",
  select: "MAX_RUN_SECONDS",
};

export function Stages() {
  // The stage machine is read from the backend rather than redrawn by hand, so
  // this section cannot drift from what a run actually does.
  const { data } = useQuery({ queryKey: ["graph"], queryFn: api.graph });

  return (
    <Section
      id="stages"
      index="02"
      title="One run, seven stages, three clocks."
      lead={
        <>
          The whole&#8209;run budget is checked between every stage and before every container. The
          model call and the container each carry their own. Resuming an interrupted run is
          deliberately out of scope &mdash; a new run is cheap and a half&#8209;resumed one is hard
          to reason about.
        </>
      }
    >
      <ol className="border-t border-line">
        {(data?.nodes ?? []).map((node, index) => (
          <li
            key={node.id}
            className="group grid grid-cols-[2rem_1fr] gap-x-5 border-b border-line py-6 sm:grid-cols-[2rem_11rem_1fr_auto] sm:gap-x-8"
          >
            <span className="font-mono text-[11px] text-muted">
              {String(index + 1).padStart(2, "0")}
            </span>
            <span className="font-display text-xl font-medium tracking-tight transition-colors group-hover:text-acid sm:text-2xl">
              {node.label}
            </span>
            <span className="col-start-2 mt-2 max-w-xl text-sm leading-relaxed text-muted sm:col-start-3 sm:mt-0">
              {node.description}
            </span>
            <span className="col-start-2 mt-2 font-mono text-[10px] text-muted/70 sm:col-start-4 sm:mt-0 sm:text-right">
              {BUDGET[node.id] ?? "—"}
            </span>
          </li>
        ))}
      </ol>
    </Section>
  );
}
