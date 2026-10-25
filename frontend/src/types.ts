// Mirrors the JSON built by src/regress/snapshot.py (build_snapshot). Display only: never recompute these values.

export type Status = "pass" | "warn" | "critical";

export interface Settings {
  warn_threshold: number;
  critical_threshold: number;
  drift_threshold: number;
  drift_window: number;
  relevance_pass_min: number;
}

export interface GoldenCase {
  id: string;
  input: string;
  expected: { category: string; summary: string };
  expected_difficulty: "easy" | "medium" | "hard";
  notes: string;
}

export interface Prompt {
  version: string;
  created_at: string;
  model: string;
  system_prompt: string;
  few_shot_examples: { email: string; output: { category: string; summary: string } }[];
}

export interface CaseResult {
  case_id: string;
  expected_category: string;
  actual_category: string | null;
  actual_summary: string | null;
  category_correct: boolean;
  relevance: number;
  latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  passed: boolean;
  error: string | null;
}

export interface Comparison {
  baseline_run_id: string | null;
  baseline_pass_rate: number | null;
  pass_rate_delta: number | null;
  category_deltas: Record<string, number>;
  regressions: string[];
  improvements: string[];
  status: Status;
}

export interface Drift {
  moving_average: number | null;
  threshold: number;
  window: number;
  drifting: boolean;
}

export interface RunView {
  run_id: string;
  created_at: string;
  prompt_version: string;
  model: string;
  dataset_version: string;
  pass_rate: number;
  category_accuracy: Record<string, number>;
  total_tokens: number;
  mean_latency_ms: number;
  cases: CaseResult[];
  comparison: Comparison;
  drift: Drift | null;
}

export interface PrRunView extends RunView {
  pr_number: number;
  head_sha: string;
}

// Props every page receives from App.
export interface PageProps {
  snapshot: Snapshot;
  datasetVersion: string;
  reload: () => Promise<void>;
}

export interface Snapshot {
  generated_at: string;
  settings: Settings;
  dataset: { version: string; cases: GoldenCase[] };
  prompts: Prompt[];
  runs: RunView[];
  pr_runs: PrRunView[];
}
