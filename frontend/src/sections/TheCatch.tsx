import { useState } from "react";
import { CHECKS } from "../lib/labels";
import { Section, TechName } from "../components/Section";

export function TheCatch() {
  const [open, setOpen] = useState<number | null>(2);

  return (
    <Section
      id="catch"
      title="The easiest way to fake a fix"
      lead="A test is a sentence about what the code should do. There are two ways to make a failing test pass, and only one of them is a repair."
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-xl border border-acid/40 bg-acid/5 p-5">
          <h3 className="font-display text-lg font-semibold text-acid">Fix the code</h3>
          <p className="mt-1 text-[15px] text-body">The honest repair. The bug is actually gone.</p>
          <pre className="mt-4 overflow-x-auto rounded-lg bg-black/40 p-4 font-mono text-[13px] leading-relaxed">
            <span className="text-muted">the test says</span>
            {"\n"}
            <span className="text-bone"> 10 items, 5 per page = 2 pages</span>
            {"\n\n"}
            <span className="text-muted">so the code was changed</span>
            {"\n"}
            <span className="text-reject">- return (total + limit) // limit</span>
            {"\n"}
            <span className="text-acid">+ return (total + limit - 1) // limit</span>
          </pre>
        </div>

        <div className="rounded-xl border border-reject/40 bg-reject/5 p-5">
          <h3 className="font-display text-lg font-semibold text-reject">Change the test</h3>
          <p className="mt-1 text-[15px] text-body">
            The test passes. The bug is still there. This is what we block.
          </p>
          <pre className="mt-4 overflow-x-auto rounded-lg bg-black/40 p-4 font-mono text-[13px] leading-relaxed">
            <span className="text-muted">the code was left alone</span>
            {"\n\n"}
            <span className="text-muted">so the test was rewritten</span>
            {"\n"}
            <span className="text-reject">- assert result == 2</span>
            {"\n"}
            <span className="text-acid">+ assert result != 2</span>
            {"\n"}
            <span className="text-muted"> # now it &quot;passes&quot;</span>
          </pre>
        </div>
      </div>

      <p className="mt-8 max-w-2xl text-body">
        The second one is not a subtle trick. It is the single most common way an automated repair
        tool cheats, and from the outside both look identical: a test that was red is now green. The
        only way to tell them apart is to check what was edited before you believe the result.
      </p>

      <h3 className="mt-14 font-display text-xl font-semibold tracking-tight">
        So every suggestion goes through nine checks first
      </h3>
      <p className="mt-2 max-w-2xl text-[15px] text-body">
        They run in order and stop at the first failure. Each one that rejects a suggestion is a
        sandbox we never had to start.
      </p>

      <ul className="mt-6 divide-y divide-line border-y border-line">
        {CHECKS.map((check, index) => {
          const expanded = open === index;
          const critical = check.technical === "no_test_edits";
          return (
            <li key={check.technical}>
              <button
                type="button"
                onClick={() => setOpen(expanded ? null : index)}
                aria-expanded={expanded}
                className="flex w-full items-baseline gap-4 py-4 text-left"
              >
                <span className="w-5 shrink-0 font-mono text-[13px] text-muted">{index + 1}</span>
                <span className="flex-1">
                  <span
                    className={`font-medium ${critical ? "text-acid" : "text-bone"}`}
                  >
                    {check.title}
                  </span>{" "}
                  <TechName>{check.technical}</TechName>
                  {expanded && (
                    <span className="mt-2 block max-w-2xl text-[15px] text-body">
                      {check.detail}
                    </span>
                  )}
                </span>
                <span className="shrink-0 font-mono text-muted" aria-hidden="true">
                  {expanded ? "−" : "+"}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}
