import { GATE_ORDER, type Gate } from "../api";

const EXPLANATIONS: Record<string, string> = {
  diff_parses: "The reply is a unified diff whose hunk headers match their bodies.",
  scope: "Every path is inside the defect's allowed_paths.",
  no_test_edits:
    "No test file is touched. Making the test agree with the code is not a fix — this is the gate that catches cheating.",
  no_new_or_deleted_files: "No creations, deletions, renames, mode changes, symlinks or binary hunks.",
  size: "The change is within MAX_DIFF_LINES.",
  syntax: "Every patched file still compiles.",
  lint: "The patch introduces no lint diagnostic the file did not already have.",
  no_new_imports: "No module is imported that the file did not already import.",
  no_dangerous_calls:
    "No newly introduced eval, exec, subprocess, socket, network or destructive filesystem call.",
};

export function GateChecklist({
  gates,
  rejectedBy,
}: {
  gates: Gate[];
  rejectedBy: string | null;
}) {
  const byName = new Map(gates.map((gate) => [gate.gate, gate]));
  const extras = gates.filter((gate) => !GATE_ORDER.includes(gate.gate as never));
  const order = [...GATE_ORDER, ...extras.map((gate) => gate.gate)];

  return (
    <ol className="space-y-1.5">
      {order.map((name, index) => {
        const gate = byName.get(name);
        const rejecting = rejectedBy === name;
        const notReached = !gate;
        const icon = notReached ? "–" : gate.passed ? "✓" : "✕";
        const tone = notReached
          ? "border-edge bg-black/20 text-muted/60"
          : gate.passed
            ? "border-pass/30 bg-pass/5 text-pass"
            : "border-fail/60 bg-fail/10 text-fail";
        return (
          <li
            key={name}
            className={`rounded-lg border px-3 py-2 ${tone} ${rejecting ? "ring-2 ring-fail/60" : ""}`}
          >
            <div className="flex items-baseline gap-2">
              <span className="w-4 select-none text-center font-bold">{icon}</span>
              <span className="w-5 select-none text-[11px] text-muted/70">{index + 1}</span>
              <code className="text-xs font-semibold">{name}</code>
              {rejecting && (
                <span className="ml-auto text-[11px] font-semibold uppercase tracking-wider">
                  rejected here
                </span>
              )}
              {notReached && (
                <span className="ml-auto text-[11px] text-muted/70">not reached</span>
              )}
            </div>
            <p className="mt-1 pl-11 text-[11px] leading-snug text-muted">
              {gate?.detail || EXPLANATIONS[name] || ""}
            </p>
          </li>
        );
      })}
    </ol>
  );
}
