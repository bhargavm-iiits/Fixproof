import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Panel } from "../components/ui";

const LIMITS = [
  {
    title: "The target application is synthetic",
    body: "Ten small pure-Python modules written for this project, with 333 tests that run in under a second. Nothing here demonstrates that the system repairs defects in a codebase it has never been evaluated against, and no such claim is made.",
  },
  {
    title: "The defects are seeded, not found in the wild",
    body: "Twenty-four defects, twelve per set, one per category. Each is a single exact snippet substitution whose break patch is proven to fail exactly one named test and no other, and whose reference patch is proven to restore a green suite.",
  },
  {
    title: "Retrieval is BM25 only",
    body: "No embeddings and no reranker. At a few hundred chunks lexical retrieval is adequate, deterministic, needs no model and keeps CI free of secrets. recall@8 is reported against what ranking found on its own, excluding the forced inclusions that would otherwise make the number 1.0 by construction. The decision reverses if it drops below 0.9.",
  },
  {
    title: "fake mode measures the harness, not a model",
    body: "MODEL_MODE=fake proposes three candidates that are meant to be rejected: one that changes nothing, one outside the allowed scope, and one that edits the failing test. A fake-mode report says so on its first page.",
  },
  {
    title: "fake_solve reads the answer key",
    body: "MODEL_MODE=fake_solve returns the fixture's own reference patch. Its fix rate is 100% by construction. The eval runner refuses to write a report from it unless --unsafe-demo is passed, and every page of such a report is stamped as not a measurement.",
  },
  {
    title: "The holdout protocol",
    body: "The dev set is used freely while iterating. The holdout set is run only against a frozen configuration, and every holdout run is recorded with its config hash. If a holdout failure causes a prompt change, that fixture is burned and must be replaced.",
  },
  {
    title: "What a verified fix actually means",
    body: "A container with no network, a read-only image, capped memory, CPU and process count, and a host-enforced timeout ran the target's own suite twice and reported that the named failing test passes and that no test which passed in the baseline now fails. Nothing else counts, however confident the model was.",
  },
  {
    title: "Explicitly out of scope",
    body: "No uploading of arbitrary repositories, no real financial data, no automatic deployment, no production authentication, no resumable runs, no multi-tenant isolation, no embedding-based retrieval and no parallel candidate verification.",
  },
];

export default function About() {
  const { data } = useQuery({ queryKey: ["graph"], queryFn: api.graph });

  return (
    <div className="space-y-6">
      <Panel
        title="How a run works"
        subtitle="The stage machine, read from the backend rather than redrawn by hand."
      >
        <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {(data?.nodes ?? []).map((node, index) => (
            <li key={node.id} className="rounded-lg border border-edge bg-black/20 px-3 py-2">
              <div className="flex items-baseline gap-2">
                <span className="text-[11px] text-muted">{index + 1}</span>
                <code className="text-xs font-semibold text-accent">{node.label}</code>
              </div>
              <p className="mt-1 text-[11px] leading-snug text-muted">{node.description}</p>
            </li>
          ))}
        </ol>
      </Panel>

      <Panel title="Honest limits" subtitle="Read these before reading anything into the numbers.">
        <div className="space-y-4">
          {LIMITS.map((limit) => (
            <article key={limit.title}>
              <h3 className="text-sm font-semibold">{limit.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-muted">{limit.body}</p>
            </article>
          ))}
        </div>
      </Panel>
    </div>
  );
}
