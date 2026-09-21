import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, STAGES, type Run } from "../api";

export type StageState = "pending" | "running" | "done";
type Event = Record<string, unknown>;

/**
 * One run at a time, the way the backend works: the API holds a semaphore of
 * one because Docker is a shared resource, so the page does too.
 */
export function useRunLifecycle() {
  const queryClient = useQueryClient();
  const [runId, setRunId] = useState<string | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const streaming = useRef<string | null>(null);

  const { data: run } = useQuery<Run>({
    queryKey: ["run", runId],
    queryFn: () => api.run(runId as string),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 1200 : false;
    },
  });

  const live = run?.status === "queued" || run?.status === "running" || (!!runId && !run);

  const start = useMutation({
    mutationFn: (defectId: string) => api.createRun(defectId),
    onSuccess: (created) => {
      setEvents([]);
      streaming.current = null;
      setRunId(created.run_id);
    },
  });

  const cancel = useCallback(() => {
    if (runId) api.cancelRun(runId).catch(() => undefined);
  }, [runId]);

  useEffect(() => {
    if (!runId || streaming.current === runId) return;
    streaming.current = runId;
    const source = new EventSource(`/runs/${encodeURIComponent(runId)}/events`);

    const handle = (raw: MessageEvent) => {
      let event: Event;
      try {
        event = JSON.parse(raw.data) as Event;
      } catch {
        return;
      }
      setEvents((previous) => [...previous, event]);
      if (event.type === "candidate" || event.type === "done" || event.terminal) {
        queryClient.invalidateQueries({ queryKey: ["run", runId] });
      }
      if (event.terminal) {
        source.close();
        queryClient.invalidateQueries({ queryKey: ["defects"] });
        queryClient.invalidateQueries({ queryKey: ["runs"] });
      }
    };

    for (const name of ["stage", "candidate", "status", "done", "error", "cancel", "message"]) {
      source.addEventListener(name, handle as EventListener);
    }
    source.onerror = () => source.close();
    return () => source.close();
  }, [runId, queryClient]);

  const stageStates: Record<string, StageState> = {};
  for (const stage of STAGES) stageStates[stage] = "pending";
  for (const event of events) {
    if (event.type !== "stage") continue;
    stageStates[String(event.stage)] = event.state === "finished" ? "done" : "running";
  }
  if (run && !live) {
    for (const stage of Object.keys(run.stage_timings)) stageStates[stage] = "done";
  }

  return { runId, run, events, live, stageStates, start, cancel, clear: () => setRunId(null) };
}
