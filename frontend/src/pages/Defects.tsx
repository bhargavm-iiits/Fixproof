import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api, type Defect } from "../api";
import { useHealth } from "../App";
import { Badge, DECISION_TONE, Empty, Panel, Spinner } from "../components/ui";

const DIFFICULTY_TONE: Record<string, string> = {
  easy: "muted",
  medium: "info",
  hard: "warn",
};

function DefectRow({ defect, canRun }: { defect: Defect; canRun: boolean }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const holdout = defect.fixture_set === "holdout";

  const start = useMutation({
    mutationFn: () => api.createRun(defect.defect_id),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      navigate(`/runs/${created.run_id}`);
    },
  });

  return (
    <tr className={`border-t border-edge ${holdout ? "bg-warn/5" : ""}`}>
      <td className="px-4 py-3 align-top">
        <div className="flex items-center gap-2">
          <code className="text-xs font-semibold">{defect.defect_id}</code>
          {holdout && (
            <Badge tone="warn" title="Running a holdout fixture is recorded">
              holdout
            </Badge>
          )}
        </div>
        <p className="mt-1 max-w-xl text-xs leading-snug text-muted">{defect.summary}</p>
      </td>
      <td className="px-4 py-3 align-top">
        <Badge tone="muted">{defect.category}</Badge>
      </td>
      <td className="px-4 py-3 align-top">
        <Badge tone={DIFFICULTY_TONE[defect.difficulty]}>{defect.difficulty}</Badge>
      </td>
      <td className="px-4 py-3 align-top">
        {defect.last_decision ? (
          <Badge tone={DECISION_TONE[defect.last_decision] ?? "muted"}>
            {defect.last_decision}
          </Badge>
        ) : (
          <span className="text-xs text-muted">never run</span>
        )}
      </td>
      <td className="px-4 py-3 text-right align-top">
        {!canRun ? (
          <span className="text-[11px] text-muted">read-only</span>
        ) : holdout && !confirming ? (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="rounded-lg border border-warn/50 px-3 py-1.5 text-xs text-warn hover:bg-warn/10"
          >
            Run holdout…
          </button>
        ) : (
          <div className="flex flex-col items-end gap-1">
            {holdout && (
              <p className="max-w-[15rem] text-right text-[11px] leading-snug text-warn">
                This run is recorded with its config hash. If you change a prompt because of what
                you see, this fixture is burned.
              </p>
            )}
            <button
              type="button"
              data-testid={`run-${defect.defect_id}`}
              disabled={start.isPending}
              onClick={() => start.mutate()}
              className="rounded-lg border border-accent/50 px-3 py-1.5 text-xs text-accent hover:bg-accent/10 disabled:opacity-50"
            >
              {start.isPending ? "starting…" : "Run"}
            </button>
          </div>
        )}
        {start.isError && <p className="mt-1 text-[11px] text-fail">{String(start.error)}</p>}
      </td>
    </tr>
  );
}

export default function Defects() {
  const [set, setSet] = useState<"all" | "dev" | "holdout">("all");
  const health = useHealth();
  const canRun = health.data?.mutations_enabled ?? false;

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["defects", set],
    queryFn: () => api.defects(set === "all" ? undefined : set),
  });

  return (
    <div className="space-y-6">
      <Panel
        title="Defects"
        subtitle="Each one is a seeded defect with a known reference fix that the model never sees."
        right={
          <div className="flex gap-1">
            {(["all", "dev", "holdout"] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setSet(option)}
                className={`rounded-lg px-2.5 py-1 text-xs ${
                  set === option ? "bg-accent/15 text-accent" : "text-muted hover:text-slate-200"
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        }
      >
        {isLoading && <Spinner label="Loading defects" />}
        {isError && <Empty>Could not reach the API: {String(error)}</Empty>}
        {data && data.length === 0 && <Empty>No fixtures in this set.</Empty>}
        {data && data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[11px] uppercase tracking-wider text-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">Defect</th>
                  <th className="px-4 py-2 font-medium">Category</th>
                  <th className="px-4 py-2 font-medium">Difficulty</th>
                  <th className="px-4 py-2 font-medium">Last decision</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody data-testid="defect-rows">
                {data.map((defect) => (
                  <DefectRow key={defect.defect_id} defect={defect} canRun={canRun} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
