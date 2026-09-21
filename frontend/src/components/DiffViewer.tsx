/**
 * A unified-diff viewer.
 *
 * Deliberately hand-written rather than pulled from a package: the format is
 * small, and the one thing this page must never do is render a patch as
 * something other than what the verifier applied.
 */
type Line = {
  kind: "add" | "del" | "ctx" | "hunk" | "file" | "meta";
  text: string;
  oldNumber?: number;
  newNumber?: number;
};

const HUNK = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/;

export function parseDiff(diff: string): Line[] {
  const lines: Line[] = [];
  let oldNumber = 0;
  let newNumber = 0;

  for (const raw of diff.replace(/\r\n/g, "\n").split("\n")) {
    if (raw.startsWith("--- ") || raw.startsWith("+++ ") || raw.startsWith("diff --git")) {
      lines.push({ kind: "file", text: raw });
      continue;
    }
    const hunk = HUNK.exec(raw);
    if (hunk) {
      oldNumber = Number(hunk[1]);
      newNumber = Number(hunk[2]);
      lines.push({ kind: "hunk", text: raw });
      continue;
    }
    if (raw.startsWith("index ") || raw.startsWith("\\")) {
      lines.push({ kind: "meta", text: raw });
      continue;
    }
    if (raw.startsWith("+")) {
      lines.push({ kind: "add", text: raw.slice(1), newNumber: newNumber++ });
    } else if (raw.startsWith("-")) {
      lines.push({ kind: "del", text: raw.slice(1), oldNumber: oldNumber++ });
    } else if (raw.length > 0 || lines.length > 0) {
      lines.push({
        kind: "ctx",
        text: raw.startsWith(" ") ? raw.slice(1) : raw,
        oldNumber: oldNumber++,
        newNumber: newNumber++,
      });
    }
  }
  return lines;
}

const STYLE: Record<Line["kind"], string> = {
  add: "bg-pass/10 text-pass",
  del: "bg-fail/10 text-fail",
  ctx: "text-slate-300",
  hunk: "bg-accent/10 text-accent",
  file: "text-muted",
  meta: "text-muted",
};

const MARK: Record<Line["kind"], string> = {
  add: "+",
  del: "-",
  ctx: " ",
  hunk: "",
  file: "",
  meta: "",
};

export function DiffViewer({ diff }: { diff: string }) {
  const lines = parseDiff(diff);
  if (lines.length === 0) {
    return <p className="text-sm text-muted">This candidate carries no diff.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-edge bg-black/40">
      <table className="w-full border-collapse font-mono text-xs leading-relaxed">
        <tbody>
          {lines.map((line, index) => (
            <tr key={index} className={STYLE[line.kind]}>
              <td className="w-12 select-none border-r border-edge px-2 text-right text-muted/60">
                {line.oldNumber ?? ""}
              </td>
              <td className="w-12 select-none border-r border-edge px-2 text-right text-muted/60">
                {line.newNumber ?? ""}
              </td>
              <td className="w-5 select-none px-1 text-center opacity-70">{MARK[line.kind]}</td>
              <td className="whitespace-pre px-2 py-px">{line.text || " "}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
