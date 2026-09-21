import { useState } from "react";
import { GATE_ORDER, type Candidate } from "../api";
import { checkLabel } from "../lib/labels";
import { DiffViewer } from "./DiffViewer";
import { Tag, TechName } from "./Section";

function Checks({ attempt }: { attempt: Candidate }) {
  const byName = new Map(attempt.gates.map((gate) => [gate.gate, gate]));
  const extras = attempt.gates.filter((gate) => !GATE_ORDER.includes(gate.gate as never));
  const order = [...GATE_ORDER, ...extras.map((gate) => gate.gate)];

  return (
    <ol className="space-y-2">
      {order.map((name) => {
        const gate = byName.get(name);
        const rejecting = attempt.rejected_by === name;
        const label = checkLabel(name);
        const mark = !gate ? "·" : gate.passed ? "✓" : "✕";
        const tone = !gate ? "text-muted/50" : gate.passed ? "text-acid" : "text-reject";
        return (
          <li
            key={name}
            className={`flex items-baseline gap-3 rounded-lg px-2 py-1 ${
              rejecting ? "bg-reject/10" : ""
            }`}
          >
            <span className={`w-4 shrink-0 text-center ${tone}`} aria-hidden="true">
              {mark}
            </span>
            <span className="flex-1">
              <span className={`text-[14px] ${gate ? "text-bone" : "text-muted/60"}`}>
                {label.title}
              </span>
              {rejecting && (
                <span className="mt-0.5 block text-[13px] text-reject">
                  Stopped here. {gate?.detail}
                </span>
              )}
            </span>
            {!gate && <span className="shrink-0 text-[13px] text-muted/50">not reached</span>}
          </li>
        );
      })}
    </ol>
  );
}

function TestResults({ attempt }: { attempt: Candidate }) {
  const verification = attempt.verification;

  if (!verification) {
    return (
      <p className="rounded-lg border border-dashed border-line p-4 text-[15px] text-body">
        This one never made it to the sandbox &mdash; a check rejected it first, which is the whole
        point of running the checks.
      </p>
    );
  }

  const broke = verification.regressions.length;

  return (
    <div className="space-y-3 text-[15px]">
      <p className={verification.target_test_passed ? "text-acid" : "text-reject"}>
        {verification.timed_out
          ? "The tests never finished — it was stopped at the time limit."
          : verification.target_test_passed
            ? "The failing test passes now."
            : "The failing test still fails."}
      </p>
      <p className={broke ? "text-reject" : "text-body"}>
        {broke === 0
          ? `Nothing else broke. All ${verification.tests_run} tests were run.`
          : `But it broke ${broke} other test${broke === 1 ? "" : "s"} that used to pass.`}
      </p>
      {broke > 0 && (
        <ul className="space-y-1">
          {verification.regressions.map((node) => (
            <li key={node} className="font-mono text-[12px] break-all text-reject">
              {node}
            </li>
          ))}
        </ul>
      )}
      <p className="text-[13px] text-muted">
        Took {(verification.duration_ms / 1000).toFixed(1)} seconds in the sandbox.
      </p>
    </div>
  );
}

export function AttemptCard({ attempt, index }: { attempt: Candidate; index: number }) {
  const [open, setOpen] = useState(false);

  const status = attempt.eligible
    ? { title: "This one worked", tone: "good" as const }
    : attempt.rejected_by
      ? { title: "Rejected before testing", tone: "bad" as const }
      : attempt.verification
        ? { title: "Tested — didn't fix it", tone: "warn" as const }
        : { title: "Not checked yet", tone: "warn" as const };

  return (
    <div
      data-testid={`attempt-${attempt.candidate_id}`}
      className={`rounded-xl border ${attempt.eligible ? "border-acid/40" : "border-line"}`}
    >
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full flex-wrap items-center gap-3 px-5 py-4 text-left"
      >
        <span className="font-medium">Attempt {index + 1}</span>
        <Tag tone={status.tone}>{status.title}</Tag>
        {attempt.rejected_by && (
          <span className="text-[14px] text-muted">
            {checkLabel(attempt.rejected_by).title.toLowerCase()}
          </span>
        )}
        <span className="ml-auto text-[14px] text-muted" aria-hidden="true">
          {open ? "Hide" : "Details"}
        </span>
      </button>

      {open && (
        <div className="space-y-8 border-t border-line px-5 py-6">
          {attempt.rationale && (
            <div>
              <h4 className="text-[13px] tracking-wide text-muted uppercase">
                What the AI said it was doing
              </h4>
              <p className="mt-1 max-w-2xl text-[15px] text-body">{attempt.rationale}</p>
            </div>
          )}

          <div>
            <h4 className="text-[13px] tracking-wide text-muted uppercase">
              What it changed &mdash; {attempt.changed_lines} line
              {attempt.changed_lines === 1 ? "" : "s"} in{" "}
              <TechName>{attempt.touched_paths.join(", ") || "nothing"}</TechName>
            </h4>
            <div className="mt-2">
              <DiffViewer diff={attempt.unified_diff} />
            </div>
          </div>

          <div className="grid gap-8 lg:grid-cols-2">
            <div>
              <h4 className="text-[13px] tracking-wide text-muted uppercase">The nine checks</h4>
              <div className="mt-2">
                <Checks attempt={attempt} />
              </div>
            </div>
            <div>
              <h4 className="text-[13px] tracking-wide text-muted uppercase">
                What the sandbox found
              </h4>
              <div className="mt-2">
                <TestResults attempt={attempt} />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
