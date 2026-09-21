import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, STAGES, type Defect } from "../api";
import { useHealth } from "../lib/health";
import { useRunLifecycle } from "../lib/useRun";
import { CandidateCard } from "../components/CandidateCard";
import { Section, Tag } from "../components/Section";

function StageTicker({
  states,
  timings,
}: {
  states: Record<string, string>;
  timings: Record<string, number>;
}) {
  return (
    <ol className="grid grid-cols-2 gap-px border border-line bg-line sm:grid-cols-4 lg:grid-cols-7">
      {STAGES.map((stage) => {
        const state = states[stage] ?? "pending";
        return (
          <li
            key={stage}
            data-stage={stage}
            data-state={state}
            className={`bg-ink px-3 py-4 ${state === "running" ? "animate-pulse" : ""}`}
          >
            <div
              className={`font-mono text-[11px] ${
                state === "done" ? "text-acid" : state === "running" ? "text-bone" : "text-muted/50"
              }`}
            >
              {stage}
            </div>
            <div className="mt-1 font-mono text-[10px] text-muted tabular-nums">
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

export function Live() {
  const [set, setSet] = useState<"dev" | "holdout">("dev");
  const [chosen, setChosen] = useState<string>("dev-off_by_one-001");
  const [confirmHoldout, setConfirmHoldout] = useState(false);

  const health = useHealth();
  const canRun = health.data?.mutations_enabled ?? false;
  const { run, live, stageStates, start, cancel } = useRunLifecycle();

  const { data: defects } = useQuery<Defect[]>({
    queryKey: ["defects", set],
    queryFn: () => api.defects(set),
  });

  const selected = defects?.find((defect) => defect.defect_id === chosen);
  const holdout = set === "holdout";
  const blocked = holdout && !confirmHoldout;

  return (
    <Section
      id="live"
      index="03"
      title="Pick a defect. Watch it get refused."
      lead={
        <>
          This runs against the live backend on this machine. In <code className="font-mono text-bone">fake</code> mode the
          three candidates are built to be rejected &mdash; that is what makes the harness testable
          without a key.
        </>
      }
    >
      <div className="space-y-8">
        <div className="flex flex-wrap items-center gap-2">
          {(["dev", "holdout"] as const).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => {
                setSet(option);
                setConfirmHoldout(false);
              }}
              className={`h-11 px-4 font-mono text-xs transition-colors ${
                set === option
                  ? "bg-bone text-ink"
                  : "border border-line text-muted hover:text-bone"
              }`}
            >
              {option}
            </button>
          ))}
          {holdout && (
            <Tag tone="reject">running a holdout fixture is recorded with its config hash</Tag>
          )}
        </div>

        <div className="grid gap-px border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
          {(defects ?? []).map((defect) => {
            const active = defect.defect_id === chosen;
            return (
              <button
                key={defect.defect_id}
                type="button"
                onClick={() => setChosen(defect.defect_id)}
                data-testid={`defect-${defect.defect_id}`}
                className={`bg-ink px-4 py-4 text-left transition-colors ${
                  active ? "bg-raised" : "hover:bg-raised"
                }`}
              >
                <div className="flex items-baseline gap-2">
                  <span
                    className={`font-mono text-[11px] ${active ? "text-acid" : "text-bone"}`}
                  >
                    {defect.category}
                  </span>
                  <span className="ml-auto font-mono text-[10px] text-muted">
                    {defect.difficulty}
                  </span>
                </div>
                <p className="mt-1.5 line-clamp-2 text-xs leading-snug text-muted">
                  {defect.summary}
                </p>
                {defect.last_decision && (
                  <p className="mt-2 font-mono text-[10px] text-muted/70">
                    last: {defect.last_decision}
                  </p>
                )}
              </button>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center gap-4">
          {!canRun ? (
            <p className="text-sm text-muted">
              This deployment is read&#8209;only. Runs shown were recorded in advance, and the
              server refuses every mutating request with a 403.
            </p>
          ) : blocked ? (
            <button
              type="button"
              onClick={() => setConfirmHoldout(true)}
              className="h-14 border border-reject/50 px-6 font-display text-lg text-reject transition-colors hover:bg-reject/10"
            >
              I understand — unlock holdout
            </button>
          ) : (
            <button
              type="button"
              data-testid="run"
              disabled={start.isPending || live}
              onClick={() => start.mutate(chosen)}
              className="group inline-flex h-14 items-center gap-4 bg-acid px-7 font-display text-lg font-medium tracking-tight text-ink transition disabled:cursor-not-allowed disabled:bg-line disabled:text-muted"
            >
              {live ? "running…" : start.isPending ? "starting…" : `run ${chosen}`}
              {!live && (
                <span className="transition-transform duration-300 group-enabled:group-hover:translate-x-1">
                  &rarr;
                </span>
              )}
            </button>
          )}
          {live && (
            <button
              type="button"
              onClick={cancel}
              className="h-14 border border-line px-5 font-mono text-xs text-muted hover:text-bone"
            >
              cancel
            </button>
          )}
          {selected && (
            <span className="min-w-0 font-mono text-[11px] break-all text-muted">
              fails {selected.failing_test}
            </span>
          )}
        </div>

        {start.isError && (
          <p className="font-mono text-xs text-reject">{String(start.error)}</p>
        )}

        {run && (
          <div className="space-y-6 border-t border-line pt-8">
            <div className="flex flex-wrap items-center gap-3">
              <span className="min-w-0 font-mono text-xs break-all text-muted">{run.run_id}</span>
              <Tag tone={run.decision === "FIX_VERIFIED" ? "acid" : run.decision ? "reject" : "muted"}>
                {run.decision ?? run.status}
              </Tag>
              {run.queue_position > 0 && <Tag>queued #{run.queue_position}</Tag>}
              {run.duration_seconds !== null && (
                <span className="font-mono text-[11px] text-muted">
                  {run.duration_seconds.toFixed(1)}s
                </span>
              )}
            </div>

            <p className="max-w-2xl text-sm leading-relaxed text-muted">
              {run.decision_explanation}
            </p>

            <StageTicker states={stageStates} timings={run.stage_timings} />

            {run.candidates.length > 0 && (
              <div className="space-y-2">
                {run.candidates.map((candidate) => (
                  <CandidateCard key={candidate.candidate_id} candidate={candidate} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </Section>
  );
}
