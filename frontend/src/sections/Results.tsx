import { useQuery } from "@tanstack/react-query";
import { api, type EvalReport } from "../api";
import { checkLabel } from "../lib/labels";
import { Section, Tag } from "../components/Section";

function pct(value: number) {
  return `${Math.round(value * 100)}%`;
}

export function Results() {
  const { data } = useQuery<EvalReport[]>({ queryKey: ["reports"], queryFn: api.reports });

  const ordered = [...(data ?? [])].sort((a, b) => a.generated_at.localeCompare(b.generated_at));
  const latest = ordered[ordered.length - 1];

  if (!latest) {
    return (
      <Section id="results" title="How well does it do?" lead="No results have been recorded yet.">
        <p className="text-[15px] text-body">Run the built-in evaluation to produce some.</p>
      </Section>
    );
  }

  const m = latest.metrics;

  const source = latest.not_a_measurement
    ? {
        tone: "bad" as const,
        text: "Not a real measurement — this run was shown the answer sheet beforehand, so of course it scored well.",
      }
    : latest.measures_a_model
      ? {
          tone: "good" as const,
          text: `These numbers come from a real AI (${latest.model_name}), over ${m.fixtures} bugs.`,
        }
      : {
          tone: "warn" as const,
          text: `These numbers come from a stand-in that deliberately makes bad suggestions. It tests the machinery, not an AI. ${m.fixtures} bugs.`,
        };

  const headline = [
    {
      value: pct(m.test_edit_attempt_rate),
      label: "of suggestions tried to change the test instead of the code",
      tone: "text-reject",
    },
    {
      value: String(m.accepted_test_edits),
      label: "of those got through",
      tone: "text-acid",
    },
    {
      value: pct(m.verified_fix_rate),
      label: "of bugs were genuinely fixed and proven",
      tone: "text-bone",
    },
  ];

  const secondary = [
    [pct(m.recall_at_8), "of the time we handed the AI the right file to look at"],
    [pct(m.gate_rejection_rate), "of suggestions were rejected before ever being tested"],
    [`${m.p95_run_seconds.toFixed(0)}s`, "the slowest run took this long"],
    [String(m.unhandled_errors), "runs crashed"],
  ];

  return (
    <Section
      id="results"
      title="How well does it do?"
      lead="The headline number here is not the fix rate. It is how often the AI tried to cheat, next to how often it succeeded."
    >
      <div className="space-y-10">
        <Tag tone={source.tone}>{source.text}</Tag>

        <dl className="grid gap-8 sm:grid-cols-3">
          {headline.map((stat) => (
            <div key={stat.label}>
              <dt className="sr-only">{stat.label}</dt>
              <dd>
                <span
                  className={`block font-display text-5xl font-semibold tracking-tight ${stat.tone}`}
                >
                  {stat.value}
                </span>
                <span className="mt-2 block text-[15px] text-body">{stat.label}</span>
              </dd>
            </div>
          ))}
        </dl>

        <dl className="grid gap-x-8 gap-y-4 border-t border-line pt-8 sm:grid-cols-2">
          {secondary.map(([value, label]) => (
            <div key={label} className="flex items-baseline gap-3">
              <dt className="sr-only">{label}</dt>
              <dd className="flex items-baseline gap-3">
                <span className="w-16 shrink-0 font-display text-xl font-semibold tabular-nums">
                  {value}
                </span>
                <span className="text-[15px] text-body">{label}</span>
              </dd>
            </div>
          ))}
        </dl>

        {Object.keys(m.rejections_by_gate).length > 0 && (
          <div className="border-t border-line pt-8">
            <h3 className="font-display text-lg font-semibold tracking-tight">
              Which check did the most work
            </h3>
            <ul className="mt-4 space-y-3">
              {Object.entries(m.rejections_by_gate).map(([gate, count]) => {
                const widest = Math.max(...Object.values(m.rejections_by_gate));
                return (
                  <li key={gate} className="flex items-center gap-4">
                    <span className="w-56 shrink-0 text-[14px] text-body">
                      {checkLabel(gate).title}
                    </span>
                    <span className="h-2 flex-1 rounded-full bg-line">
                      <span
                        className="block h-2 rounded-full bg-acid"
                        style={{ width: `${(count / widest) * 100}%` }}
                      />
                    </span>
                    <span className="w-8 shrink-0 text-right text-[14px] text-muted tabular-nums">
                      {count}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        <div className="border-t border-line pt-8">
          <h3 className="font-display text-lg font-semibold tracking-tight">
            What we check on every change
          </h3>
          <p className="mt-2 max-w-2xl text-[15px] text-body">
            These run automatically. They test whether the machinery works, not whether the AI is
            clever.
          </p>
          <ul className="mt-4 space-y-2">
            {latest.checks.map((check) => (
              <li key={check.name} className="flex items-baseline gap-3">
                <span
                  className={`w-4 shrink-0 text-center ${check.passed ? "text-acid" : "text-reject"}`}
                  aria-hidden="true"
                >
                  {check.passed ? "✓" : "✕"}
                </span>
                <span className="text-[14px] text-body">
                  {check.name}
                  <span className="sr-only">{check.passed ? " — passed" : " — failed"}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Section>
  );
}
