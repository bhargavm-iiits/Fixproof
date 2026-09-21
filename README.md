# fixproof

**An AI says it fixed the bug. Did it?**

fixproof takes a program with a known bug, asks an AI to repair it, and then
checks the answer the only way that counts — by running the program's own tests
inside a sealed container with no network access.

If the tests don't pass, it isn't a fix. It doesn't matter how confident the
model sounded.

---

## The problem this exists for

There are two ways to make a failing test pass.

```diff
  # Fix the code — the bug is actually gone
- return (total + limit) // limit
+ return (total + limit - 1) // limit
```

```diff
  # Change the test — the bug is still there
- assert result == 2
+ assert result != 2   # now it "passes"
```

From the outside these are indistinguishable: a test that was red is now green.
The second is the single most common way an automated repair tool cheats, and
the only way to tell them apart is to check *what was edited* before believing
the result.

So fixproof reports two numbers side by side:

| | |
|---|---|
| How often a suggestion tried to edit the test | **the cheating rate** |
| How often one succeeded | **0**, asserted in CI on every push |

---

## Quickstart

Requires Python 3.12, Docker (Linux containers), Node 24, and Git.

```bash
# 1. Install
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.in     # Windows
# python3.12 -m venv .venv && .venv/bin/pip install -r requirements.in   # Linux/macOS

cp .env.example .env

# 2. Build the sandbox image
docker build -f docker/verifier.Dockerfile -t fixproof-verifier:1 .

# 3. Build the site
cd frontend && npm ci && npm run build && cd ..

# 4. Run it
.venv/Scripts/python.exe -m uvicorn backend.app.main:app --port 8000
```

Open <http://127.0.0.1:8000>. Pick a bug, press **Fix this bug**, and watch every
suggestion get checked. API docs are at `/docs`.

No API key is needed: the default `MODEL_MODE=fake` uses a stand-in that makes
deliberately bad suggestions, which is what lets the safety machinery be tested
for free. To use a real model, set `MODEL_MODE=gemini`, `GEMINI_API_KEY` and
`GEMINI_MODEL`.

---

## How a run works

```
prepare → baseline → retrieve → propose → gate → verify → select
```

| Step | What it does |
|---|---|
| **prepare** | Copy the target program and apply the bug, so every run starts identically |
| **baseline** | Run the full suite *before* touching anything, so "broke something else" is a computation rather than a guess |
| **retrieve** | Rank the codebase with BM25, then force-include the failing test and the editable file |
| **propose** | Ask the model for up to `MAX_CANDIDATES` patches, each a distinct hypothesis |
| **gate** | Nine ordered static checks, short-circuiting on the first rejection |
| **verify** | Run the suite in a container: no network, read-only image, capped memory/CPU/PIDs, host-enforced kill |
| **select** | Among eligible patches: fewest lines, then fewest files, then confidence. Fully deterministic |

Three independent budgets are enforced: the whole run, each model call, and each
container.

### The nine checks

Ordered, short-circuiting. Each rejection saves a container, and the reason
becomes a metric.

1. `diff_parses` — the reply is a real unified diff whose hunk headers match their bodies
2. `scope` — no path outside the bug's `allowed_paths`
3. **`no_test_edits`** — no test file is touched *(the one that matters)*
4. `no_new_or_deleted_files` — no creations, deletions, renames, modes or symlinks
5. `size` — within `MAX_DIFF_LINES`
6. `syntax` — every patched file still compiles
7. `lint` — no diagnostic the file didn't already carry
8. `no_new_imports` — nothing newly imported
9. `no_dangerous_calls` — no new `eval`, `exec`, subprocess, socket or destructive write

Checks 7 and 8 are measured **against the broken baseline**, so a correct repair
is never punished for untidiness it inherited.

---

## What "verified" means

A container with no network, a read-only image, capped memory, CPU and process
count, and a kill from the host ran the target's own suite twice and reported
that the named failing test passes and that **no test which passed in the
baseline now fails**.

Nothing else counts. Model confidence is not an input to that decision.

---

## Honesty machinery

This project is as much about not fooling yourself as about repairing code.

- **`MODEL_MODE=fake`** proposes deliberately rejectable patches. Any report from
  it is stamped *measures the harness, not a model*.
- **`MODEL_MODE=fake_solve`** returns the fixture's own reference patch, so its
  fix rate is 100% by construction. The eval runner **refuses to write a report**
  from it without `--unsafe-demo`, and stamps every page that results.
- **`recall_at_8`** is measured against what ranking found *on its own*, excluding
  the forced inclusions — otherwise it would read 1.0 by construction and could
  never trigger the decision to add a reranker.
- **Cost** is reported as *unavailable* rather than as a confident `$0.00` when
  token prices aren't configured.
- **Holdout protocol**: the dev set is used freely while iterating. The holdout
  set runs only against a frozen configuration, and every run records its
  `config_hash`. If a holdout failure causes a prompt change, that fixture is
  burned and must be replaced.

---

## Testing

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m pytest backend/tests -q          # 437 tests
.venv/Scripts/python.exe -m pytest verifier/tests -q -m docker
.venv/Scripts/python.exe scripts/validate_fixtures.py --set dev
.venv/Scripts/python.exe evals/run_eval.py --set dev --gate
cd frontend && npx playwright test                            # end-to-end
```

Every fixture is *proven* before use: its break patch must fail exactly one
named test and no other, and its reference patch must restore a green suite.

After any run, this must print nothing:

```bash
docker ps -a --filter name=fixproof- --format '{{.Names}}'
```

---

## Layout

```
backend/app/services/    the pipeline: retrieval, model clients, gates,
                         workspaces, verifier, selection, orchestrator
backend/app/api/         FastAPI surface; demo mode answers 403, never 404
target_app/              the program being repaired: 10 modules, 333 tests
fixtures/dev|holdout/    24 proven bugs, one per category per set
docker/                  the sandbox image and its in-container runner
evals/                   the eval runner and its quality gate
frontend/                the site
docs/decisions.md        every design decision with what would reverse it
```

---

## What this doesn't prove

- The target program is **one we wrote** — ten small pure-Python modules. Nothing
  here shows the approach works on a large, messy, real codebase, and no such
  claim is made.
- The bugs are **planted**, and the correct fix for each is known in advance.
- Retrieval is **BM25 only** — no embeddings, no reranker. Adequate at this size;
  `recall_at_8` is reported so the moment it stops being adequate is visible.
- Out of scope by choice: arbitrary repository uploads, resumable runs,
  multi-tenant isolation, parallel candidate verification.

Design decisions, each with the condition that would reverse it, are in
[`docs/decisions.md`](docs/decisions.md).
