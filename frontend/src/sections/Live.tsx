import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, STAGES, type Defect } from "../api";
import { useHealth } from "../lib/health";
import { useRunLifecycle } from "../lib/useRun";
import { categoryLabel, DIFFICULTY, outcomeOf, STEP_BY_NAME } from "../lib/labels";
import { AttemptCard } from "../components/AttemptCard";
import { Section, Tag } from "../components/Section";

function Progress({ states }: { states: Record<string, string> }) {
  const done = STAGES.filter((stage) => states[stage] === "done").length;
  const running = STAGES.find((stage) => states[stage] === "running");
  const current = running ? STEP_BY_NAME.get(running) : null;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-4">
        <p className="text-[15px] text-body">
          {current ? current.title : done === STAGES.length ? "Finished." : "Starting…"}
        </p>
        <span className="text-[13px] text-muted tabular-nums">
          {done} of {STAGES.length}
        </span>
      </div>
      <ol className="mt-3 flex gap-1" aria-label="Progress through the run">
        {STAGES.map((stage) => {
          const state = states[stage] ?? "pending";
          return (
            <li
              key={stage}
              data-stage={stage}
              data-state={state}
              title={STEP_BY_NAME.get(stage)?.title ?? stage}
              className={`h-1.5 flex-1 rounded-full ${
                state === "done"
                  ? "bg-acid"
                  : state === "running"
                    ? "animate-pulse bg-bone"
                    : "bg-line"
              }`}
            />
          );
        })}
      </ol>
    </div>
  );
}

export function Live() {
  const [set, setSet] = useState<"dev" | "holdout">("dev");
  const [chosen, setChosen] = useState("dev-off_by_one-001");

  const health = useHealth();
  const canRun = health.data?.mutations_enabled ?? false;
  const { run, live, stageStates, start, cancel } = useRunLifecycle();

  const { data: bugs } = useQuery<Defect[]>({
    queryKey: ["defects", set],
    queryFn: () => api.defects(set),
  });

  const selected = bugs?.find((bug) => bug.defect_id === chosen);
  const outcome = run ? outcomeOf(run.decision, run.status) : null;
  const worked = run?.candidates.filter((attempt) => attempt.eligible).length ?? 0;

  return (
    <Section
      id="try"
      title="Try it yourself"
      lead="Pick a bug and watch the whole thing happen. It takes about five seconds, and it runs on this machine — nothing is pre-recorded."
    >
      <div className="space-y-8">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[14px] text-muted">Show:</span>
            {(
              [
                ["dev", "Practice bugs"],
                ["holdout", "Held-back bugs"],
              ] as const
            ).map(([option, label]) => (
              <button
                key={option}
                type="button"
                onClick={() => setSet(option)}
                aria-pressed={set === option}
                className={`h-10 rounded-lg px-4 text-[14px] transition ${
                  set === option
                    ? "bg-bone text-ink"
                    : "border border-line text-body hover:border-bone/40"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {set === "holdout" && (
            <p className="mt-3 max-w-2xl text-[14px] text-body">
              These are kept aside and only used to measure. Looking at how they fail and then
              tweaking the system would quietly turn honest measurement into wishful thinking, so
              every run of these is recorded.
            </p>
          )}
        </div>

        <fieldset>
          <legend className="text-[14px] text-muted">Choose a bug</legend>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {(bugs ?? []).map((bug) => {
              const active = bug.defect_id === chosen;
              return (
                <button
                  key={bug.defect_id}
                  type="button"
                  onClick={() => setChosen(bug.defect_id)}
                  aria-pressed={active}
                  data-testid={`bug-${bug.defect_id}`}
                  className={`rounded-xl border p-4 text-left transition ${
                    active ? "border-acid/60 bg-acid/5" : "border-line hover:border-bone/30"
                  }`}
                >
                  <div className="flex items-baseline gap-2">
                    <span className={`font-medium ${active ? "text-acid" : "text-bone"}`}>
                      {categoryLabel(bug.category)}
                    </span>
                    <span className="ml-auto text-[13px] text-muted">
                      {DIFFICULTY[bug.difficulty] ?? bug.difficulty}
                    </span>
                  </div>
                  <p className="mt-1 text-[14px] text-body">{bug.summary}</p>
                </button>
              );
            })}
          </div>
        </fieldset>

        <div className="flex flex-wrap items-center gap-4">
          {!canRun ? (
            <p className="text-[15px] text-body">
              This copy is read-only, so the run button isn&rsquo;t available here.
            </p>
          ) : (
            <button
              type="button"
              data-testid="run"
              disabled={start.isPending || live}
              onClick={() => start.mutate(chosen)}
              className="inline-flex h-12 items-center rounded-lg bg-acid px-6 font-medium text-ink transition hover:brightness-110 disabled:bg-line disabled:text-muted"
            >
              {live ? "Working…" : start.isPending ? "Starting…" : "Fix this bug"}
            </button>
          )}
          {live && (
            <button
              type="button"
              onClick={cancel}
              className="h-12 rounded-lg border border-line px-5 text-[15px] text-body hover:border-bone/40"
            >
              Stop
            </button>
          )}
          {selected && !live && !run && (
            <p className="text-[14px] text-muted">
              The AI will see the broken file and the test that fails.
            </p>
          )}
        </div>

        {start.isError && (
          <p className="text-[15px] text-reject">
            Couldn&rsquo;t start the run. Is the sandbox available?
          </p>
        )}

        {run && outcome && (
          <div className="space-y-6 rounded-xl border border-line p-5 sm:p-6">
            <Progress states={stageStates} />

            <div className="border-t border-line pt-5">
              <div className="flex flex-wrap items-center gap-3">
                <h3 className="font-display text-xl font-semibold tracking-tight">
                  {outcome.title}
                </h3>
                <Tag tone={outcome.tone}>
                  {run.candidates.length} attempt{run.candidates.length === 1 ? "" : "s"}
                </Tag>
                {run.duration_seconds !== null && (
                  <span className="text-[13px] text-muted">
                    {run.duration_seconds.toFixed(1)}s
                  </span>
                )}
              </div>
              <p className="mt-2 max-w-2xl text-[15px] text-body">{outcome.detail}</p>
              {worked > 0 && (
                <p className="mt-2 max-w-2xl text-[15px] text-acid">
                  The winning edit changed{" "}
                  {run.candidates.find((a) => a.eligible)?.changed_lines} line
                  {run.candidates.find((a) => a.eligible)?.changed_lines === 1 ? "" : "s"}.
                </p>
              )}
            </div>

            {run.candidates.length > 0 && (
              <div className="space-y-2 border-t border-line pt-5">
                <p className="text-[13px] tracking-wide text-muted uppercase">
                  What the AI suggested
                </p>
                {run.candidates.map((attempt, index) => (
                  <AttemptCard key={attempt.candidate_id} attempt={attempt} index={index} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </Section>
  );
}
