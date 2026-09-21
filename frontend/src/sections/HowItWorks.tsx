import { useState } from "react";
import { STEPS } from "../lib/labels";
import { Section, TechName } from "../components/Section";

const HEADLINE = [
  {
    title: "Something is broken",
    body: "We take a small working program, introduce one specific bug, and confirm that exactly one test now fails.",
  },
  {
    title: "The AI suggests repairs",
    body: "It sees the broken file and the failing test, and offers two or three different ideas about what's wrong.",
  },
  {
    title: "We check, then we prove",
    body: "Nine fast checks throw out the obviously bad answers. Whatever survives gets run against the real tests in a sandbox.",
  },
];

export function HowItWorks() {
  const [showDetail, setShowDetail] = useState(false);

  return (
    <Section
      id="how"
      title="How it works"
      lead="Three things happen. The third one is the part nobody else does."
    >
      <ol className="grid gap-8 sm:grid-cols-3">
        {HEADLINE.map((step, index) => (
          <li key={step.title}>
            <span className="font-mono text-[13px] text-acid">Step {index + 1}</span>
            <h3 className="mt-2 font-display text-xl font-semibold tracking-tight">{step.title}</h3>
            <p className="mt-2 text-[15px] text-body">{step.body}</p>
          </li>
        ))}
      </ol>

      <div className="mt-12 border-t border-line pt-8">
        <button
          type="button"
          onClick={() => setShowDetail(!showDetail)}
          aria-expanded={showDetail}
          className="flex items-center gap-2 text-[15px] text-bone hover:text-acid"
        >
          <span aria-hidden="true">{showDetail ? "−" : "+"}</span>
          {showDetail ? "Hide the detail" : "Show what actually happens, step by step"}
        </button>

        {showDetail && (
          <ol className="mt-6 space-y-5">
            {STEPS.map((step, index) => (
              <li key={step.technical} className="flex gap-4">
                <span className="w-6 shrink-0 pt-0.5 font-mono text-[13px] text-muted">
                  {index + 1}
                </span>
                <div>
                  <h4 className="font-medium text-bone">
                    {step.title} <TechName>{step.technical}</TechName>
                  </h4>
                  <p className="mt-1 text-[15px] text-body">{step.detail}</p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </Section>
  );
}
