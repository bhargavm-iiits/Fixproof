import { Section } from "../components/Section";

const LIMITS: [string, string][] = [
  [
    "The target application is synthetic",
    "Ten small pure-Python modules written for this project, with 333 tests that run in under a second. Nothing here demonstrates that the system repairs defects in a codebase it has never been evaluated against, and no such claim is made.",
  ],
  [
    "The defects are seeded, not found in the wild",
    "Twenty-four defects, twelve per set, one per category. Each is a single exact snippet substitution whose break patch is proven to fail exactly one named test and no other, and whose reference patch is proven to restore a green suite.",
  ],
  [
    "Retrieval is BM25 only",
    "No embeddings and no reranker. At a few hundred chunks lexical retrieval is adequate, deterministic and needs no model. recall@8 is reported against what ranking found on its own — excluding the forced inclusions that would otherwise make the number 1.0 by construction. The decision reverses below 0.9.",
  ],
  [
    "fake mode measures the harness",
    "It proposes three candidates meant to be rejected: one that changes nothing, one outside the allowed scope, one that edits the failing test. A fake-mode report says so on its first page.",
  ],
  [
    "fake_solve reads the answer key",
    "It returns the fixture's own reference patch, so its fix rate is 100% by construction. The eval runner refuses to write a report from it without --unsafe-demo, and stamps every page that results.",
  ],
  [
    "The holdout protocol",
    "The dev set is used freely while iterating. The holdout set runs only against a frozen configuration, and every holdout run is recorded with its config hash. If a holdout failure causes a prompt change, that fixture is burned and must be replaced.",
  ],
  [
    "What a verified fix actually means",
    "A container with no network, a read-only image, capped memory, CPU and process count, and a kill from the host ran the target's own suite twice and reported that the named failing test passes and that no test which passed in the baseline now fails. Nothing else counts, however confident the model was.",
  ],
  [
    "Explicitly out of scope",
    "No uploading of arbitrary repositories, no real financial data, no automatic deployment, no production authentication, no resumable runs, no multi-tenant isolation, no embedding-based retrieval, no parallel candidate verification.",
  ],
];

export function Limits() {
  return (
    <Section
      id="limits"
      index="05"
      title="What this does not show."
      lead="Read these before reading anything into the numbers above."
    >
      <div className="grid gap-x-16 gap-y-10 sm:grid-cols-2">
        {LIMITS.map(([title, body]) => (
          <article key={title}>
            <h3 className="font-display text-lg font-medium tracking-tight text-bone">{title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">{body}</p>
          </article>
        ))}
      </div>
    </Section>
  );
}
