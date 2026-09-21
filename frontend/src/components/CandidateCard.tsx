import { useState } from "react";
import { GATE_ORDER, type Candidate } from "../api";
import { DiffViewer } from "./DiffViewer";
import { Tag } from "./Section";

function GateList({ candidate }: { candidate: Candidate }) {
  const byName = new Map(candidate.gates.map((gate) => [gate.gate, gate]));
  const extras = candidate.gates.filter((gate) => !GATE_ORDER.includes(gate.gate as never));
  const order = [...GATE_ORDER, ...extras.map((gate) => gate.gate)];

  return (
    <ol className="divide-y divide-line border-y border-line">
      {order.map((name, index) => {
        const gate = byName.get(name);
        const rejecting = candidate.rejected_by === name;
        const mark = !gate ? "–" : gate.passed ? "✓" : "✕";
        const tone = !gate ? "text-muted/50" : gate.passed ? "text-acid" : "text-reject";
        return (
          <li
            key={name}
            className={`flex items-baseline gap-3 py-2.5 ${rejecting ? "bg-reject/8 -mx-3 px-3" : ""}`}
          >
            <span className="w-5 shrink-0 font-mono text-[10px] text-muted/60">
              {String(index + 1).padStart(2, "0")}
            </span>
            <span className={`w-4 shrink-0 text-center font-bold ${tone}`}>{mark}</span>
            <span className="flex-1">
              <span
                className={`block font-mono text-xs ${gate ? "text-bone" : "text-muted/60"}`}
              >
                {name}
              </span>
              {gate?.detail && (
                <span className="mt-0.5 block text-[11px] leading-snug text-muted">
                  {gate.detail}
                </span>
              )}
            </span>
            {rejecting && (
              <span className="shrink-0 font-mono text-[10px] tracking-wider text-reject uppercase">
                rejected here
              </span>
            )}
            {!gate && (
              <span className="shrink-0 font-mono text-[10px] text-muted/50">not reached</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function Verification({ candidate }: { candidate: Candidate }) {
  const verification = candidate.verification;
  if (!verification) {
    return (
      <div className="border border-dashed border-line px-5 py-6">
        <p className="font-display text-lg font-medium tracking-tight">No container was started</p>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          A static gate rejected this candidate first, which is exactly the point of running them:
          each rejection saves a container, and the reason it gave is recorded as a metric rather
          than thrown away.
        </p>
      </div>
    );
  }

  const rows: [string, string, string?][] = [
    [
      "target test",
      verification.timed_out
        ? "timed out"
        : verification.target_test_passed
          ? "passes"
          : "still fails",
      verification.target_test_passed && !verification.timed_out ? "text-acid" : "text-reject",
    ],
    ["tests run", String(verification.tests_run)],
    ["duration", `${verification.duration_ms} ms`],
    ["container exit code", verification.container_exit_code === null ? "killed" : String(verification.container_exit_code)],
  ];

  return (
    <div className="space-y-4">
      <dl className="divide-y divide-line border-y border-line">
        {rows.map(([label, value, tone]) => (
          <div key={label} className="flex items-baseline justify-between py-2.5">
            <dt className="font-mono text-[11px] tracking-wider text-muted uppercase">{label}</dt>
            <dd className={`font-mono text-xs ${tone ?? "text-bone"}`}>{value}</dd>
          </div>
        ))}
      </dl>

      <div>
        <div className="font-mono text-[11px] tracking-wider text-muted uppercase">regressions</div>
        {verification.regressions.length === 0 ? (
          <p className="mt-1 font-mono text-xs text-acid">none</p>
        ) : (
          <ul className="mt-1 space-y-1">
            {verification.regressions.map((node) => (
              <li key={node} className="font-mono text-xs break-all text-reject">
                {node}
              </li>
            ))}
          </ul>
        )}
      </div>

      {verification.newly_passing.length > 0 && (
        <div>
          <div className="font-mono text-[11px] tracking-wider text-muted uppercase">
            newly passing
          </div>
          <ul className="mt-1 space-y-1">
            {verification.newly_passing.map((node) => (
              <li key={node} className="font-mono text-xs break-all text-acid">
                {node}
              </li>
            ))}
          </ul>
        </div>
      )}

      {verification.stdout_tail && (
        <details className="group">
          <summary className="cursor-pointer font-mono text-[11px] tracking-wider text-muted uppercase">
            output tail
          </summary>
          <pre className="mt-2 max-h-56 overflow-auto border border-line bg-black/40 p-3 font-mono text-[11px] leading-snug whitespace-pre-wrap text-bone/70">
            {verification.stdout_tail}
          </pre>
        </details>
      )}
    </div>
  );
}

export function CandidateCard({ candidate }: { candidate: Candidate }) {
  const [open, setOpen] = useState(false);
  const tone = candidate.eligible ? "acid" : candidate.rejected_by ? "reject" : "muted";
  const verdict = candidate.eligible
    ? "verified fix"
    : candidate.rejected_by
      ? `rejected by ${candidate.rejected_by}`
      : candidate.verification
        ? "ran, not eligible"
        : "proposed";

  return (
    <div
      data-testid={`candidate-${candidate.candidate_id}`}
      className={`border ${candidate.eligible ? "border-acid/40" : "border-line"}`}
    >
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full flex-wrap items-center gap-3 px-5 py-4 text-left"
      >
        <span className="font-mono text-xs text-bone">{candidate.candidate_id}</span>
        <Tag tone={tone}>{verdict}</Tag>
        <span className="min-w-0 font-mono text-[11px] break-all text-muted">
          {candidate.changed_lines} lines · {candidate.touched_paths.join(", ") || "—"}
        </span>
        <span
          className={`ml-auto font-mono text-lg text-muted transition-transform duration-300 ${open ? "rotate-45" : ""}`}
          aria-hidden="true"
        >
          +
        </span>
      </button>

      {open && (
        <div className="border-t border-line px-5 py-5">
          {candidate.rationale && (
            <p className="mb-5 max-w-2xl text-sm leading-relaxed text-muted">
              {candidate.rationale}
            </p>
          )}
          <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
            <div>
              <div className="mb-2 font-mono text-[11px] tracking-wider text-muted uppercase">
                the diff
              </div>
              <DiffViewer diff={candidate.unified_diff} />
            </div>
            <div className="space-y-6">
              <div>
                <div className="mb-2 font-mono text-[11px] tracking-wider text-muted uppercase">
                  gates
                </div>
                <GateList candidate={candidate} />
              </div>
              <div>
                <div className="mb-2 font-mono text-[11px] tracking-wider text-muted uppercase">
                  verification
                </div>
                <Verification candidate={candidate} />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
