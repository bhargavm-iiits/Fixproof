import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, STAGES, type Candidate } from "../api";
import { useHealth } from "../App";
import { StageTimeline, type StageState } from "../components/StageTimeline";
import { Badge, DECISION_TONE, Empty, Panel, Spinner, Stat } from "../components/ui";

type Event = Record<string, unknown>;

function useRunEvents(runId: string, live: boolean) {
  const [events, setEvents] = useState<Event[]>([]);
  const queryClient = useQueryClient();
  const seen = useRef(false);

  useEffect(() => {
    if (!live || seen.current) return;
    seen.current = true;
    const source = new EventSource(`/runs/${encodeURIComponent(runId)}/events`);
    const handle = (raw: MessageEvent) => {
      try {
        const event = JSON.parse(raw.data) as Event;
        setEvents((previous) => [...previous, event]);
        if (event.terminal) {
          source.close();
          queryClient.invalidateQueries({ queryKey: ["run", runId] });
        }
        if (event.type === "candidate" || event.type === "done") {
          queryClient.invalidateQueries({ queryKey: ["run", runId] });
        }
      } catch {
        /* a malformed frame is not worth tearing the page down for */
      }
    };
    for (const name of ["stage", "candidate", "status", "done", "error", "message"]) {
      source.addEventListener(name, handle as EventListener);
    }
    source.onerror = () => source.close();
    return () => source.close();
  }, [runId, live, queryClient]);

  return events;
}

function CandidateCard({ runId, candidate }: { runId: string; candidate: Candidate }) {
  const verification = candidate.verification;
  const tone = candidate.eligible ? "pass" : candidate.rejected_by ? "fail" : "warn";
  return (
    <Link
      to={`/runs/${runId}/candidates/${candidate.candidate_id}`}
      data-testid={`candidate-${candidate.candidate_id}`}
      className="block rounded-xl border border-edge bg-black/20 p-4 transition hover:border-accent/50"
    >
      <div className="flex flex-wrap items-center gap-2">
        <code className="text-xs font-semibold">{candidate.candidate_id}</code>
        <Badge tone={tone}>
          {candidate.eligible ? "verified fix" : candidate.rejected_by ? "gated" : "not eligible"}
        </Badge>
        <span className="ml-auto text-[11px] text-muted">
          round {candidate.round_index} · {candidate.changed_lines} lines
        </span>
      </div>
      {candidate.rationale && (
        <p className="mt-2 text-xs leading-snug text-muted">{candidate.rationale}</p>
      )}
      <dl className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
        <div>
          <dt className="text-muted">Rejected by</dt>
          <dd className={candidate.rejected_by ? "text-fail" : "text-muted"}>
            <code>{candidate.rejected_by ?? "nothing"}</code>
          </dd>
        </div>
        <div>
          <dt className="text-muted">Target test</dt>
          <dd
            className={
              !verification ? "text-muted" : verification.target_test_passed ? "text-pass" : "text-fail"
            }
          >
            {!verification
              ? "never ran"
              : verification.timed_out
                ? "timed out"
                : verification.target_test_passed
                  ? "passes"
                  : "still fails"}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Regressions</dt>
          <dd className={verification?.regressions.length ? "text-fail" : "text-muted"}>
            {verification ? verification.regressions.length : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Touches</dt>
          <dd className="truncate text-muted">
            <code>{candidate.touched_paths.join(", ") || "—"}</code>
          </dd>
        </div>
      </dl>
    </Link>
  );
}

export default function RunPage() {
  const { runId = "" } = useParams();
  const health = useHealth();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.run(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 1500 : false;
    },
  });

  const live = data?.status === "queued" || data?.status === "running";
  const events = useRunEvents(runId, live ?? false);

  const stageStates = useMemo(() => {
    const states: Record<string, StageState> = {};
    for (const stage of STAGES) states[stage] = "pending";
    for (const event of events) {
      if (event.type !== "stage") continue;
      const stage = String(event.stage);
      states[stage] = event.state === "finished" ? "done" : "running";
    }
    if (data && !live) {
      for (const stage of Object.keys(data.stage_timings)) states[stage] = "done";
    }
    return states;
  }, [events, data, live]);

  if (isLoading) return <Spinner label="Loading run" />;
  if (isError || !data) return <Empty>No such run.</Empty>;

  const canCancel = live && (health.data?.mutations_enabled ?? false);

  return (
    <div className="space-y-6">
      <Panel
        title={<code className="text-sm">{data.run_id}</code>}
        subtitle={
          <>
            <Link to="/" className="text-accent hover:underline">
              {data.defect_id}
            </Link>{" "}
            · {data.fixture_set} set · {data.model_mode} mode · config {data.config_hash.slice(0, 8)}
          </>
        }
        right={
          <div className="flex items-center gap-2">
            {data.decision ? (
              <Badge tone={DECISION_TONE[data.decision] ?? "muted"}>{data.decision}</Badge>
            ) : (
              <Badge tone="info">{data.status}</Badge>
            )}
            {canCancel && (
              <button
                type="button"
                onClick={() => api.cancelRun(runId)}
                className="rounded-lg border border-edge px-2.5 py-1 text-xs text-muted hover:text-slate-200"
              >
                Cancel
              </button>
            )}
          </div>
        }
      >
        <p className="text-sm text-muted">{data.decision_explanation}</p>
        {data.timeout_stage && (
          <p className="mt-2 text-sm text-fail">
            The run ended during the <code>{data.timeout_stage}</code> stage.
          </p>
        )}
        {data.error && <p className="mt-2 text-sm text-fail">{data.error}</p>}
        {data.queue_position > 0 && (
          <p className="mt-2 text-sm text-warn">
            Queued at position {data.queue_position}. One run executes at a time, because Docker is
            a shared resource.
          </p>
        )}
        <div className="mt-4">
          <StageTimeline states={stageStates} timings={data.stage_timings} />
        </div>
      </Panel>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Candidates" value={data.candidates.length} />
        <Stat
          label="Gated"
          value={data.candidates.filter((c) => c.rejected_by).length}
          hint="Rejected before a container started"
        />
        <Stat
          label="Verified fix"
          value={data.chosen_candidate_id ? "yes" : "no"}
          tone={data.chosen_candidate_id ? "pass" : "warn"}
          hint={data.chosen_candidate_id ?? "no candidate was eligible"}
        />
        <Stat
          label="Duration"
          value={data.duration_seconds ? `${data.duration_seconds.toFixed(1)}s` : "—"}
          hint={`${data.rounds_used} round(s)`}
        />
      </div>

      <Panel
        title="Candidates"
        subtitle="A rejected candidate with its rejecting gate named shows the part of the system that does the work."
      >
        {data.candidates.length === 0 ? (
          <Empty>No candidates yet.</Empty>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {data.candidates.map((candidate) => (
              <CandidateCard key={candidate.candidate_id} runId={runId} candidate={candidate} />
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
