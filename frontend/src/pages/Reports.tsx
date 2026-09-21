import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type EvalReport } from "../api";
import { Badge, Empty, Panel, Spinner, Stat } from "../components/ui";

const AXIS = { stroke: "#8fa0c0", fontSize: 11 };
const GRID = "#22304f";

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function Stamp({ report }: { report: EvalReport }) {
  if (report.not_a_measurement) {
    return (
      <div className="rounded-lg border border-fail/40 bg-fail/10 px-4 py-3 text-sm text-fail">
        <strong>Not a measurement.</strong> This report was produced with{" "}
        <code>MODEL_MODE=fake_solve</code>, which reads each fixture&rsquo;s reference patch. Its
        fix rate is 100% by construction.
      </div>
    );
  }
  if (!report.measures_a_model) {
    return (
      <div className="rounded-lg border border-warn/40 bg-warn/10 px-4 py-3 text-sm text-warn">
        This report was produced with <code>MODEL_MODE=fake</code>, which proposes deliberately
        rejectable patches. <strong>It measures the harness, not a model.</strong>
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-accent">
      This report measures <code>{report.model_name}</code> at config hash{" "}
      <code>{report.config_hash}</code>.
    </div>
  );
}

export default function Reports() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["reports"],
    queryFn: api.reports,
  });

  if (isLoading) return <Spinner label="Loading reports" />;
  if (isError) return <Empty>Could not reach the API.</Empty>;
  if (!data || data.length === 0) {
    return (
      <Empty>
        No eval reports have been committed yet. Run{" "}
        <code>python evals/run_eval.py --set dev --gate</code>.
      </Empty>
    );
  }

  const ordered = [...data].sort((a, b) => a.generated_at.localeCompare(b.generated_at));
  const latest = ordered[ordered.length - 1];
  const metrics = latest.metrics;

  const trend = ordered.map((report) => ({
    at: report.generated_at.slice(5, 16).replace("T", " "),
    set: report.fixture_set,
    verified: report.metrics.verified_fix_rate * 100,
    cheating: report.metrics.test_edit_attempt_rate * 100,
    gated: report.metrics.gate_rejection_rate * 100,
    recall: report.metrics.recall_at_8 * 100,
    p95: report.metrics.p95_run_seconds,
  }));

  const byGate = Object.entries(metrics.rejections_by_gate).map(([gate, count]) => ({
    gate,
    count,
  }));

  return (
    <div className="space-y-6">
      <Panel
        title="Latest eval"
        subtitle={`${latest.fixture_set} set · ${latest.generated_at} · ${metrics.fixtures} fixtures`}
        right={<Badge tone="muted">{latest.report_file}</Badge>}
      >
        <Stamp report={latest} />
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat
            label="Verified fix rate"
            value={percent(metrics.verified_fix_rate)}
            tone={metrics.verified_fix_rate > 0 ? "pass" : "warn"}
          />
          <Stat
            label="Test-edit attempt rate"
            value={percent(metrics.test_edit_attempt_rate)}
            tone="warn"
            hint="How often the model tried to edit the test"
          />
          <Stat
            label="Accepted test edits"
            value={metrics.accepted_test_edits}
            tone={metrics.accepted_test_edits === 0 ? "pass" : "fail"}
            hint="How often it got away with it"
          />
          <Stat
            label="Recall@8"
            value={percent(metrics.recall_at_8)}
            hint="Ranking alone, excluding forced inclusions"
          />
          <Stat label="Gate rejection rate" value={percent(metrics.gate_rejection_rate)} />
          <Stat label="Regression rate" value={percent(metrics.regression_rate)} />
          <Stat
            label="p95 run seconds"
            value={metrics.p95_run_seconds.toFixed(1)}
            hint={`mean ${metrics.mean_run_seconds.toFixed(1)}s`}
          />
          <Stat
            label="Cost"
            value={metrics.priced && metrics.cost_usd !== null ? `$${metrics.cost_usd.toFixed(4)}` : "n/a"}
            hint={metrics.priced ? undefined : "token prices not configured"}
          />
        </div>
      </Panel>

      <Panel
        title="Quality gate"
        subtitle="These assert mechanism, not model quality."
      >
        <ul className="space-y-1.5" data-testid="checks">
          {latest.checks.map((check) => (
            <li
              key={check.name}
              className={`flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
                check.passed
                  ? "border-pass/30 bg-pass/5 text-pass"
                  : "border-fail/60 bg-fail/10 text-fail"
              }`}
            >
              <span className="w-4 text-center font-bold">{check.passed ? "✓" : "✕"}</span>
              <span>{check.name}</span>
              <span className="ml-auto text-[11px] opacity-80">
                actual {String(check.actual)} · required {String(check.required)}
              </span>
            </li>
          ))}
        </ul>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Rejections by gate" subtitle="Which gate does the most work.">
          {byGate.length === 0 ? (
            <Empty>Nothing was rejected.</Empty>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={byGate}>
                <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
                <XAxis dataKey="gate" tick={AXIS} angle={-20} textAnchor="end" height={70} />
                <YAxis tick={AXIS} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: "#121a2e", border: `1px solid ${GRID}` }}
                  labelStyle={{ color: "#e8eefc" }}
                />
                <Bar dataKey="count" fill="#6ea8ff" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Panel>

        <Panel title="Trends" subtitle="Across every committed report.">
          {trend.length < 2 ? (
            <Empty>Two or more committed reports are needed before a trend means anything.</Empty>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={trend}>
                <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
                <XAxis dataKey="at" tick={AXIS} />
                <YAxis tick={AXIS} />
                <Tooltip
                  contentStyle={{ background: "#121a2e", border: `1px solid ${GRID}` }}
                  labelStyle={{ color: "#e8eefc" }}
                />
                <Line type="monotone" dataKey="verified" name="verified %" stroke="#3ddc97" />
                <Line type="monotone" dataKey="cheating" name="test-edit %" stroke="#ffc857" />
                <Line type="monotone" dataKey="gated" name="gated %" stroke="#ff6b6b" />
                <Line type="monotone" dataKey="recall" name="recall@8 %" stroke="#6ea8ff" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Panel>
      </div>

      <Panel title="Decisions" subtitle="How each fixture ended.">
        <div className="flex flex-wrap gap-2">
          {Object.entries(metrics.decisions).map(([decision, count]) => (
            <Badge key={decision} tone="muted">
              {decision}: {count}
            </Badge>
          ))}
        </div>
      </Panel>
    </div>
  );
}
