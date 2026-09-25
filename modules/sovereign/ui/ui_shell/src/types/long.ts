/**
 * LONG route (sharded inference): big-model runs split into fresh-context chunks that carry
 * only a small ledger. Types for the operator's composer and the read-only run view served by
 * `GET /v1/jobs/<id>/ledger`.
 */

export interface LongModelInfo {
  model: string;
  context: number;
  thinking: string;
}

/** From `/v1/health`: whether LONG can run here and which models it may use. */
export interface LongRouteInfo {
  ready: boolean;
  defaultModel?: string;
  models: LongModelInfo[];
  error?: string;
}

/** What the operator attaches to a LONG objective. */
export type LongInputMode = "plan" | "material" | "inbox";

export interface LongOptions {
  model: string;
  mode: LongInputMode;
  material: string;
  inboxFile: string;
}

export type LongTaskStatus = "pending" | "completed" | "failed";

export interface LongTask {
  task_id: string;
  kind: string;
  status: LongTaskStatus;
  attempts: number;
  summary: string | null;
  error: string | null;
  utc: string | null;
}

export interface LongLedger {
  facts: string[];
  decisions: string[];
  open_questions: string[];
  results: { task: string; summary: string }[];
}

export interface LongRunView {
  job_id: string;
  started: boolean;
  job_status?: string;
  mode?: string;
  objective?: string;
  run_status?: string;
  model_calls?: number;
  completed?: number;
  failed?: number;
  total?: number;
  tasks: LongTask[];
  ledger: LongLedger | null;
}
