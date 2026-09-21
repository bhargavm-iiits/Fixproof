import { useQuery } from "@tanstack/react-query";
import { api, type EvalReport } from "../api";
import { Section, Tag } from "../components/Section";

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export function Evidence() {
  const { data } = useQuery<EvalReport[]>({ queryKey: ["reports"], queryFn: api.reports });

  const ordered = [...(data ?? [])].sort((a, b) => a.generated_at.localeCompare(b.generated_at));
  const latest = ordered[ordered.length - 1];

  if (!latest) {
    return (
      <Section
        id="evidence"
        index="04"
        title="What it measured."
        lead="No eval report has been committed yet."
      >
        <p className="font-mono text-sm text-muted">
          python evals/run_eval.py --set dev --gate
        </p>
      </Section>
    );
  }

  const metrics = latest.metrics;
  const stamp = latest.not_a_measurement
    ? {
        tone: "reject" as const,
        text: "Produced with MODEL_MODE=fake_solve, which reads each fixture's reference patch. Its fix rate is 100% by construction. This is not a measurement.",
      }
    : latest.measures_a_model
      ? {
          tone: "acid" as const,
          text: `Measures ${latest.model_name} at config hash ${latest.config_hash}.`,
        }
      : {
          tone: "muted" as const,
          text: "Produced with MODEL_MODE=fake, which proposes deliberately rejectable patches. This measures the harness, not a model.",
        };

  const headline: [string, string, string?][] = [
    [percent(metrics.test_edit_attempt_rate), "tried to edit the test", "text-reject"],
    [String(metrics.accepted_test_edits), "got away with it", "text-acid"],
    [percent(metrics.verified_fix_rate), "verified fix rate"],
    [percent(metrics.recall_at_8), "recall@8, ranking alone"],
    [`${metrics.p95_run_seconds.toFixed(1)}s`, "p95 run seconds"],
    [String(metrics.unhandled_errors), "unhandled errors"],
  ];

  return (
    <Section
      id="evidence"
      index="04"
      title="Attempted against accepted."
      lead={
        <>
          The number to lead with is not the fix rate. It is how often a candidate tried to edit the
          failing test, set against how often one succeeded. The second number is the one the CI
          gate asserts.
        </>
      }
    >
      <div className="space-y-10">
        <Tag tone={stamp.tone}>{stamp.text}</Tag>

        <div className="grid grid-cols-2 gap-px border border-line bg-line sm:grid-cols-3">
          {headline.map(([value, label, tone]) => (
            <div key={label} className="bg-ink px-5 py-7">
              <div
                className={`font-display text-3xl font-semibold tracking-tight sm:text-4xl ${tone ?? "text-bone"}`}
              >
                {value}
              </div>
              <div className="mt-2 text-xs leading-snug text-muted">{label}</div>
            </div>
          ))}
        </div>

        <div>
          <div className="mb-3 font-mono text-[11px] tracking-wider text-muted uppercase">
            quality gate — asserts mechanism, not model quality
          </div>
          <ul className="grid gap-px border border-line bg-line sm:grid-cols-2">
            {latest.checks.map((check) => (
              <li key={check.name} className="flex items-baseline gap-3 bg-ink px-4 py-3">
                <span
                  className={`shrink-0 font-bold ${check.passed ? "text-acid" : "text-reject"}`}
                >
                  {check.passed ? "✓" : "✕"}
                </span>
                <span className="flex-1 text-xs leading-snug text-muted">{check.name}</span>
                <span className="shrink-0 font-mono text-[10px] text-muted/70">
                  {String(check.actual)}
                </span>
              </li>
            ))}
          </ul>
        </div>

        {Object.keys(metrics.rejections_by_gate).length > 0 && (
          <div>
            <div className="mb-3 font-mono text-[11px] tracking-wider text-muted uppercase">
              which gate does the work
            </div>
            <ul className="space-y-2">
              {Object.entries(metrics.rejections_by_gate).map(([gate, count]) => {
                const widest = Math.max(...Object.values(metrics.rejections_by_gate));
                return (
                  <li key={gate} className="flex items-center gap-4">
                    <span className="w-48 shrink-0 font-mono text-xs text-bone">{gate}</span>
                    <span className="h-3 flex-1 bg-line">
                      <span
                        className="block h-3 bg-acid"
                        style={{ width: `${(count / widest) * 100}%` }}
                      />
                    </span>
                    <span className="w-8 shrink-0 text-right font-mono text-xs text-muted tabular-nums">
                      {count}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {ordered.length > 1 && (
          <p className="font-mono text-[11px] text-muted">
            {ordered.length} committed reports · latest {latest.report_file}
          </p>
        )}
      </div>
    </Section>
  );
}
