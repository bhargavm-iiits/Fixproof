export type Health = {
  status: string;
  app_mode: "local" | "demo";
  model_mode: "fake" | "fake_solve" | "gemini";
  model_name: string;
  config_hash: string;
  docker_reachable: boolean;
  image: string;
  image_present: boolean;
  leaked_containers: number;
  schema_version: number;
  mutations_enabled: boolean;
};

export type Defect = {
  defect_id: string;
  fixture_set: "dev" | "holdout";
  summary: string;
  failing_test: string;
  allowed_paths: string[];
  category: string;
  difficulty: "easy" | "medium" | "hard";
  last_decision: string | null;
};

export type Gate = { gate: string; passed: boolean; detail: string };

export type Verification = {
  candidate_id: string;
  container_exit_code: number | null;
  target_test_passed: boolean;
  regressions: string[];
  newly_passing: string[];
  tests_run: number;
  duration_ms: number;
  stdout_tail: string;
  timed_out: boolean;
};

export type Candidate = {
  candidate_id: string;
  round_index: number;
  rationale: string;
  unified_diff: string;
  touched_paths: string[];
  changed_lines: number;
  confidence: number;
  status: string;
  rejected_by: string | null;
  eligible: boolean;
  gates: Gate[];
  verification: Verification | null;
};

export type Run = {
  run_id: string;
  defect_id: string;
  fixture_set: string;
  status: string;
  decision: string | null;
  decision_explanation: string;
  chosen_candidate_id: string | null;
  queue_position: number;
  model_mode: string;
  model_name: string;
  config_hash: string;
  rounds_used: number;
  timeout_stage: string | null;
  error: string | null;
  stage_timings: Record<string, number>;
  duration_seconds: number | null;
  usage: {
    calls: number;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number | null;
    priced: boolean;
  };
  candidates: Candidate[];
  artifacts: string[];
};

export type RunSummary = {
  run_id: string;
  defect_id: string;
  fixture_set: string;
  status: string;
  decision: string | null;
  chosen_candidate_id: string | null;
  model_mode: string;
  config_hash: string;
  started_at: string | null;
  finished_at: string | null;
};

export type EvalReport = {
  generated_at: string;
  fixture_set: string;
  model_mode: string;
  model_name: string;
  config_hash: string;
  measures_a_model: boolean;
  not_a_measurement: boolean;
  report_file?: string;
  metrics: {
    fixtures: number;
    decisions: Record<string, number>;
    verified_fix_rate: number;
    regression_rate: number;
    candidates_proposed: number;
    gate_rejection_rate: number;
    rejections_by_gate: Record<string, number>;
    test_edit_attempts: number;
    test_edit_attempt_rate: number;
    accepted_test_edits: number;
    candidates_to_first_fix: number;
    recall_at_8: number;
    mean_changed_lines: number;
    mean_reference_changed_lines: number;
    rounds_used_mean: number;
    round_2_rescue_rate: number;
    mean_run_seconds: number;
    p95_run_seconds: number;
    unhandled_errors: number;
    terminal_decision_rate: number;
    model_calls: number;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number | null;
    priced: boolean;
  };
  checks: { name: string; actual: unknown; required: unknown; passed: boolean }[];
};

export type GraphNode = { id: string; label: string; description: string };

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      /* the body was not JSON; the status text will have to do */
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/healthz"),
  defects: (set?: string) =>
    request<Defect[]>(`/defects${set ? `?set=${encodeURIComponent(set)}` : ""}`),
  defect: (id: string) => request<Defect>(`/defects/${encodeURIComponent(id)}`),
  runs: (limit = 25) => request<{ total: number; runs: RunSummary[] }>(`/runs?limit=${limit}`),
  run: (id: string) => request<Run>(`/runs/${encodeURIComponent(id)}`),
  createRun: (defectId: string) =>
    request<{ run_id: string; queue_position: number }>("/runs", {
      method: "POST",
      body: JSON.stringify({ defect_id: defectId }),
    }),
  cancelRun: (id: string) =>
    request<{ run_id: string }>(`/runs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  reports: () => request<EvalReport[]>("/reports"),
  graph: () => request<{ stages: string[]; nodes: GraphNode[] }>("/graph"),
};

export const STAGES = [
  "prepare",
  "baseline",
  "retrieve",
  "propose",
  "gate",
  "verify",
  "select",
] as const;

export const GATE_ORDER = [
  "diff_parses",
  "scope",
  "no_test_edits",
  "no_new_or_deleted_files",
  "size",
  "syntax",
  "lint",
  "no_new_imports",
  "no_dangerous_calls",
] as const;
