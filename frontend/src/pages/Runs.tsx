import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Badge, DECISION_TONE, Empty, Panel, Spinner } from "../components/ui";

export default function Runs() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["runs"],
    queryFn: () => api.runs(50),
    refetchInterval: 5_000,
  });

  return (
    <Panel title="Runs" subtitle="Newest first. Every run keeps its own artifact directory.">
      {isLoading && <Spinner label="Loading runs" />}
      {isError && <Empty>Could not reach the API.</Empty>}
      {data && data.runs.length === 0 && (
        <Empty>No runs yet. Start one from the Defects page.</Empty>
      )}
      {data && data.runs.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-[11px] uppercase tracking-wider text-muted">
              <tr>
                <th className="px-4 py-2 font-medium">Run</th>
                <th className="px-4 py-2 font-medium">Defect</th>
                <th className="px-4 py-2 font-medium">Set</th>
                <th className="px-4 py-2 font-medium">Decision</th>
                <th className="px-4 py-2 font-medium">Mode</th>
                <th className="px-4 py-2 font-medium">Started</th>
              </tr>
            </thead>
            <tbody>
              {data.runs.map((run) => (
                <tr key={run.run_id} className="border-t border-edge">
                  <td className="px-4 py-2">
                    <Link to={`/runs/${run.run_id}`} className="text-accent hover:underline">
                      <code className="text-xs">{run.run_id}</code>
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <code className="text-xs text-muted">{run.defect_id}</code>
                  </td>
                  <td className="px-4 py-2">
                    <Badge tone={run.fixture_set === "holdout" ? "warn" : "muted"}>
                      {run.fixture_set}
                    </Badge>
                  </td>
                  <td className="px-4 py-2">
                    {run.decision ? (
                      <Badge tone={DECISION_TONE[run.decision] ?? "muted"}>{run.decision}</Badge>
                    ) : (
                      <Badge tone="muted">{run.status}</Badge>
                    )}
                  </td>
                  <td className="px-4 py-2 text-xs text-muted">{run.model_mode}</td>
                  <td className="px-4 py-2 text-xs tabular-nums text-muted">
                    {run.started_at?.replace("T", " ").slice(0, 19) ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
