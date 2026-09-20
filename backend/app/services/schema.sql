-- fixproof persistence. Plain sqlite3, no ORM: one writer, a handful of queries,
-- and fewer dependencies to defend. Reverse that on concurrent writers or a
-- second consumer of this data.

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id              TEXT PRIMARY KEY,
    defect_id           TEXT NOT NULL,
    fixture_set         TEXT NOT NULL,
    status              TEXT NOT NULL,
    decision            TEXT,
    chosen_candidate_id TEXT,
    model_mode          TEXT NOT NULL,
    model_name          TEXT NOT NULL DEFAULT '',
    config_hash         TEXT NOT NULL DEFAULT '',
    rounds_used         INTEGER NOT NULL DEFAULT 0,
    timeout_stage       TEXT,
    error               TEXT,
    stage_timings       TEXT NOT NULL DEFAULT '{}',
    started_at          TEXT,
    finished_at         TEXT,
    artifact_dir        TEXT NOT NULL DEFAULT ''
);

-- A candidate id is only unique inside its run: every run of the fake client
-- produces `r1-noop`. The key is the pair.
CREATE TABLE IF NOT EXISTS candidates (
    run_id        TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    candidate_id  TEXT NOT NULL,
    round_index   INTEGER NOT NULL,
    rationale     TEXT NOT NULL DEFAULT '',
    -- The diff itself, so a restored run is self-contained and the API can serve
    -- a candidate without reaching into the artifact directory by path.
    unified_diff  TEXT NOT NULL DEFAULT '',
    changed_lines INTEGER NOT NULL,
    touched_paths TEXT NOT NULL DEFAULT '[]',
    confidence    REAL NOT NULL DEFAULT 0.0,
    status        TEXT NOT NULL,
    PRIMARY KEY (run_id, candidate_id)
);

CREATE TABLE IF NOT EXISTS gate_results (
    run_id       TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    position     INTEGER NOT NULL,
    gate         TEXT NOT NULL,
    passed       INTEGER NOT NULL,
    detail       TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (run_id, candidate_id, position),
    FOREIGN KEY (run_id, candidate_id)
        REFERENCES candidates(run_id, candidate_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS verifications (
    run_id             TEXT NOT NULL,
    candidate_id       TEXT NOT NULL,
    target_test_passed INTEGER NOT NULL,
    regressions        TEXT NOT NULL DEFAULT '[]',
    newly_passing      TEXT NOT NULL DEFAULT '[]',
    tests_run          INTEGER NOT NULL DEFAULT 0,
    duration_ms        INTEGER NOT NULL DEFAULT 0,
    timed_out          INTEGER NOT NULL DEFAULT 0,
    exit_code          INTEGER,
    stdout_tail        TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (run_id, candidate_id),
    FOREIGN KEY (run_id, candidate_id)
        REFERENCES candidates(run_id, candidate_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS usage (
    run_id        TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
    calls         INTEGER NOT NULL DEFAULT 0,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd      REAL,
    priced        INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS runs_by_defect ON runs(defect_id, started_at DESC);
CREATE INDEX IF NOT EXISTS runs_by_started ON runs(started_at DESC);
CREATE INDEX IF NOT EXISTS gate_results_by_gate ON gate_results(gate, passed);
