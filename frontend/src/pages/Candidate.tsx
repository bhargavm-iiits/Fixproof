import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { DiffViewer } from "../components/DiffViewer";
import { GateChecklist } from "../components/GateChecklist";
import { Badge, Empty, Panel, Spinner, Stat } from "../components/ui";

export default function CandidatePage() {
  const { runId = "", candidateId = "" } = useParams();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.run(runId),
  });

  if (isLoading) return <Spinner label="Loading candidate" />;
  if (isError || !data) return <Empty>No such run.</Empty>;

  const candidate = data.candidates.find((entry) => entry.candidate_id === candidateId);
  if (!candidate) return <Empty>No such candidate in this run.</Empty>;

  const verification = candidate.verification;

  return (
    <div className="space-y-6">
      <Panel
        title={<code className="text-sm">{candidate.candidate_id}</code>}
        subtitle={
          <>
            <Link to={`/runs/${runId}`} className="text-accent hover:underline">
              back to the run
            </Link>{" "}
            · round {candidate.round_index} · confidence{" "}
            {(candidate.confidence * 100).toFixed(0)}%
          </>
        }
        right={
          <Badge tone={candidate.eligible ? "pass" : candidate.rejected_by ? "fail" : "warn"}>
            {candidate.eligible
              ? "verified fix"
              : candidate.rejected_by
                ? `rejected by ${candidate.rejected_by}`
                : "not eligible"}
          </Badge>
        }
      >
        {candidate.rationale ? (
          <p className="text-sm text-muted">{candidate.rationale}</p>
        ) : (
          <p className="text-sm text-muted">This candidate offered no rationale.</p>
        )}
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <Stat label="Changed lines" value={candidate.changed_lines} />
          <Stat label="Files touched" value={candidate.touched_paths.length} hint={candidate.touched_paths.join(", ")} />
          <Stat
            label="Reached a container"
            value={verification ? "yes" : "no"}
            tone={verification ? "pass" : "warn"}
            hint={verification ? undefined : "a gate rejected it first, so no container was started"}
          />
        </div>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <Panel title="The diff" subtitle="Exactly what would be applied, as the verifier received it.">
          <DiffViewer diff={candidate.unified_diff} />
        </Panel>

        <div className="space-y-6">
          <Panel
            title="Gates"
            subtitle="Ordered and short-circuiting. Each rejection saves a container."
          >
            <GateChecklist gates={candidate.gates} rejectedBy={candidate.rejected_by} />
          </Panel>

          <Panel title="Verification" subtitle="The only component permitted to declare a fix.">
            {!verification ? (
              <Empty>
                No container was started: a gate rejected this candidate first.
              </Empty>
            ) : (
              <dl className="space-y-3 text-sm" data-testid="verification">
                <div className="flex items-center justify-between">
                  <dt className="text-muted">Target test</dt>
                  <dd>
                    <Badge tone={verification.target_test_passed ? "pass" : "fail"}>
                      {verification.timed_out
                        ? "timed out"
                        : verification.target_test_passed
                          ? "passes"
                          : "still fails"}
                    </Badge>
                  </dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-muted">Tests run</dt>
                  <dd className="tabular-nums">{verification.tests_run}</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-muted">Duration</dt>
                  <dd className="tabular-nums">{verification.duration_ms} ms</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-muted">Container exit code</dt>
                  <dd className="tabular-nums">{verification.container_exit_code ?? "killed"}</dd>
                </div>
                <div>
                  <dt className="text-muted">Regressions</dt>
                  <dd className="mt-1">
                    {verification.regressions.length === 0 ? (
                      <span className="text-pass">none</span>
                    ) : (
                      <ul className="space-y-1">
                        {verification.regressions.map((node) => (
                          <li key={node} className="font-mono text-xs text-fail">
                            {node}
                          </li>
                        ))}
                      </ul>
                    )}
                  </dd>
                </div>
                {verification.newly_passing.length > 0 && (
                  <div>
                    <dt className="text-muted">Newly passing</dt>
                    <dd className="mt-1">
                      <ul className="space-y-1">
                        {verification.newly_passing.map((node) => (
                          <li key={node} className="font-mono text-xs text-pass">
                            {node}
                          </li>
                        ))}
                      </ul>
                    </dd>
                  </div>
                )}
                {verification.stdout_tail && (
                  <div>
                    <dt className="text-muted">Output tail</dt>
                    <dd className="mt-1 max-h-64 overflow-auto rounded-lg border border-edge bg-black/40 p-3">
                      <pre className="whitespace-pre-wrap text-[11px] leading-snug text-slate-300">
                        {verification.stdout_tail}
                      </pre>
                    </dd>
                  </div>
                )}
              </dl>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
