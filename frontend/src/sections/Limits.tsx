import { Section } from "../components/Section";

const LIMITS: [string, string][] = [
  [
    "The program being fixed is one we wrote",
    "Ten small files and 333 tests, built for this project. Nothing here shows that the same approach works on a large, messy, real codebase — and we don't claim it does.",
  ],
  [
    "The bugs were planted on purpose",
    "Twenty-four of them, and we know the correct fix for each one in advance. Every planted bug is checked to make sure it breaks exactly one test and nothing else.",
  ],
  [
    "The AI never sees the answer",
    "The known-good fix is used only for scoring. It is never put in front of the AI — with one clearly-labelled exception used for testing the plumbing, which is why any result from that mode is stamped as not a measurement.",
  ],
  [
    "Finding the right file is done simply",
    "We match words, rather than using anything cleverer. At this size that works fine, and we measure how often it hands over the right file so the moment it stops working will be visible.",
  ],
  [
    "Some runs use a stand-in, not a real AI",
    "The stand-in deliberately makes bad suggestions, including one that tries to change the test. It exists so the safety machinery can be tested without spending money, and any results from it say so.",
  ],
  [
    "What 'proven' actually means here",
    "A sealed sandbox — no internet, limited memory, a hard time limit — ran the program's own tests twice and reported that the broken test now passes and nothing that passed before now fails. That is the entire claim. Nothing else counts.",
  ],
];

export function Limits() {
  return (
    <Section
      id="limits"
      title="What this doesn't prove"
      lead="Worth reading before you take any of the numbers above too seriously."
    >
      <div className="grid gap-x-12 gap-y-8 sm:grid-cols-2">
        {LIMITS.map(([title, body]) => (
          <article key={title}>
            <h3 className="font-medium text-bone">{title}</h3>
            <p className="mt-1.5 text-[15px] text-body">{body}</p>
          </article>
        ))}
      </div>
    </Section>
  );
}
