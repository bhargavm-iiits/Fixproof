# Decisions

One short entry each, with the condition that would reverse it. A decision with
no reversal condition is a habit, not a decision.

## 1. Python 3.12 everywhere, locally and in containers

The host had 3.14 registered and nothing else. Pinning 3.12 on both sides means a
result reproduced in a container is a result reproducible locally.

**Reverse when** a dependency the project needs requires something newer.

## 2. `docker cp` rather than a bind mount

Bind mounts drag Windows path translation into every verification. Copying
sidesteps it entirely and makes the container's view of the code a snapshot the
host cannot change mid-run.

**Reverse if** throughput ever matters more than portability.

## 3. No network in the verifier

Dependencies are baked into the image so the container can run with
`--network none`. A patch cannot reach the internet, and a run cannot be
perturbed by a package index.

**Do not reverse.** Bake new dependencies into the image instead.

## 4. `/work` is a throwaway volume, not the container's root filesystem

The workbook specifies both `--read-only` and `docker cp` into `/work`. Docker
refuses `docker cp` into a read-only rootfs outright — the daemon answers
`container rootfs is marked read-only` before it looks at the destination — and a
`--tmpfs /work` would be mounted over the copied files at start. A per-container
volume keeps both halves of the intent: the image stays read-only, and the code
under test still arrives as a copied snapshot. The volume is removed in the same
`finally` block as the container, and CI asserts that neither leaks.

**Reverse when** Docker permits `cp` into a read-only container.

## 5. BM25 only, no embeddings and no reranker

At a few hundred chunks, lexical retrieval is adequate, deterministic, needs no
model and keeps CI free of secrets.

**Reverse when** `recall_at_8` drops below 0.9. The eval reports it against what
ranking found *on its own*, excluding the forced inclusions — otherwise the
metric would read 1.0 by construction and could never trigger this reversal.

## 6. Plain `sqlite3`, no ORM

One writer, a handful of queries, fewer dependencies to defend.

**Reverse on** concurrent writers, or a second consumer of the data.

## 7. `MAX_PROPOSE_ROUNDS=1`

A second round doubles model cost and its value is unknown until measured.

**Reverse when** `round_2_rescue_rate` justifies the cost. Turning a loop on
before you can measure it is how a project acquires costs nobody can defend.

## 8. Static gates duplicate prompt rules

Every rule in the system prompt is enforced again, independently, after the reply
arrives.

**Do not reverse.** A prompt is not an enforcement mechanism.

## 9. No resumable runs

A new run is cheap; a half-resumed run is hard to reason about.

**Reverse when** a single run routinely exceeds a few minutes.

## 10. `ProposedPatch` and `CandidatePatch` are two types

The workbook asks for a model that rejects a diff touching `tests/`, *and* for a
fake candidate that edits the failing test so the `no_test_edits` gate can reject
it and the cheating rate can be counted. Both cannot hold for one type: a patch
that cannot be constructed cannot be rejected, and a rejection that cannot be
represented cannot be measured.

So `ProposedPatch` is the permissive transport type — it still re-derives
`touched_paths` and `changed_lines` from the diff, so a model can never
misdescribe its own patch — and `CandidatePatch` adds the path policy. Only
`CandidatePatch` values are ever applied.

**Reverse if** the gate results stop being reported as metrics, at which point
one strict type would do.

## 11. The `scope` gate ignores test paths

A test edit is also out of scope, so ordering `scope` before `no_test_edits`
would report every attempted test edit as a generic scope violation and destroy
the one number worth leading with. `scope` therefore complains only about
non-test paths, and test paths are left to the gate that exists to name them.

**Do not reverse** while `test_edit_attempt_rate` is a reported metric.

## 12. The `lint` and `no_new_imports` gates are measured against the baseline

Only newly introduced diagnostics count. Two fixtures seed a mutable default
argument, which ruff flags; rejecting a correct repair because the file it
repairs was already untidy would make the gate actively harmful.

**Do not reverse.** A gate that punishes a fix for a pre-existing problem stops
measuring the fix.

## 13. The model client is given the contents of the editable files

The workbook's `propose` signature omits them, but its prompt specification lists
"the current contents of each file in `allowed_paths`" as required context, and a
model cannot write an applicable diff against a file it has not seen.

**Reverse if** retrieval is ever guaranteed to include every editable file in
full, at which point the retrieval result alone would be enough.

## 14. Candidate diffs are stored in the database, not only in artifacts

The workbook's `candidates` table lists no diff column. Storing it makes a
restored run self-contained, lets the API serve a candidate without joining a
client-supplied path onto an artifact directory, and costs a few hundred bytes.

**Reverse if** diffs ever grow large enough for the row size to matter.

## 15. `candidates` is keyed on `(run_id, candidate_id)`

A candidate id is only unique inside its run: every fake-mode run produces
`r1-noop`.

**Do not reverse.**

## 16. The API's artifact route serves an allow-list of names

The client never supplies a path. Anything outside the allow-list is a 404,
including a name that would traverse.

**Do not reverse.**

## 17. Demo mode answers 403, not 404

A 404 would be a lie about the route existing. The body names `APP_MODE=demo` so
the caller knows the deployment is read-only rather than broken.

**Do not reverse.**
