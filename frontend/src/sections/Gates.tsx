import { useState } from "react";
import { Section, Tag } from "../components/Section";

const GATES: { name: string; blurb: string; detail: string; critical?: boolean }[] = [
  {
    name: "diff_parses",
    blurb: "The reply really is a unified diff.",
    detail:
      "Every hunk header has to agree with the body beneath it. A header that lies about its line counts would swallow the next file's headers and hide a second touched path from every check that follows, so this runs first and refuses it.",
  },
  {
    name: "scope",
    blurb: "Nothing outside the declared paths.",
    detail:
      "Every path must sit inside the defect's allowed_paths — except test paths, which are deliberately left for the next gate. Reporting a test edit as a generic scope violation would bury the one number worth leading with.",
  },
  {
    name: "no_test_edits",
    blurb: "Making the test agree with the code is not a fix.",
    detail:
      "The most common way an automated fixer cheats is by editing the test. The rate at which candidates reach this gate is the cheating rate. The rate at which any gets past it is zero, and CI asserts that on every push.",
    critical: true,
  },
  {
    name: "no_new_or_deleted_files",
    blurb: "No creations, deletions, renames, modes or symlinks.",
    detail:
      "Including ones smuggled in alongside a legitimate edit — a valid hunk on an allowed file followed by a quiet rename is still refused.",
  },
  {
    name: "size",
    blurb: "Within MAX_DIFF_LINES.",
    detail:
      "A repair for a one-line defect that rewrites forty lines is not a minimal repair, whatever it does to the failing test.",
  },
  {
    name: "syntax",
    blurb: "Every patched file still compiles.",
    detail: "Cheap to check here. Expensive to discover inside a container.",
  },
  {
    name: "lint",
    blurb: "No diagnostic the file did not already carry.",
    detail:
      "Measured against the broken baseline on purpose. Two fixtures seed a mutable default argument, which ruff flags; rejecting a correct repair for a mess it inherited would make the gate actively harmful.",
  },
  {
    name: "no_new_imports",
    blurb: "Nothing imported that was not imported before.",
    detail: "Also baseline-relative, for the same reason.",
  },
  {
    name: "no_dangerous_calls",
    blurb: "No new eval, exec, subprocess, socket or destructive write.",
    detail:
      "With scope and no_test_edits, one of the three gates that exist for safety rather than tidiness. Newly introduced only — a call the file already made is not this patch's doing.",
    critical: true,
  },
];

export function Gates() {
  const [open, setOpen] = useState<number | null>(2);

  return (
    <Section
      id="gates"
      index="01"
      title="Nine ways to be refused before anything runs."
      lead={
        <>
          The gates are ordered and short&#8209;circuiting: the first refusal ends the sequence, and
          every one of them duplicates a rule the prompt already asked for. That duplication is the
          point &mdash; a prompt is not an enforcement mechanism.
        </>
      }
    >
      <ul className="border-t border-line">
        {GATES.map((gate, index) => {
          const expanded = open === index;
          return (
            <li key={gate.name} className="border-b border-line">
              <button
                type="button"
                onClick={() => setOpen(expanded ? null : index)}
                aria-expanded={expanded}
                className="group flex w-full items-baseline gap-5 py-6 text-left transition-colors sm:gap-8"
              >
                <span className="w-8 shrink-0 font-mono text-[11px] text-muted">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="flex-1">
                  <span
                    className={`block font-display text-xl font-medium tracking-tight transition-colors sm:text-2xl ${
                      expanded ? "text-acid" : "text-bone group-hover:text-acid"
                    }`}
                  >
                    {gate.name}
                  </span>
                  <span className="mt-1 block text-sm text-muted">{gate.blurb}</span>
                  {expanded && (
                    <span className="mt-4 block max-w-2xl text-sm leading-relaxed text-bone/70">
                      {gate.detail}
                    </span>
                  )}
                </span>
                {gate.critical && (
                  <span className="hidden shrink-0 sm:block">
                    <Tag tone="reject">security</Tag>
                  </span>
                )}
                <span
                  className={`shrink-0 font-mono text-lg text-muted transition-transform duration-300 ${
                    expanded ? "rotate-45" : ""
                  }`}
                  aria-hidden="true"
                >
                  +
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}
