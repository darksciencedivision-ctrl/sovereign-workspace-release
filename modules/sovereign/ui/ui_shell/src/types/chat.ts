export type MessageRole = "user" | "sovereign";

export type RouteOverride =
  | "AUTO"
  | "STATUS"
  | "QUICK"
  | "DEEP"
  | "RESEARCH"
  | "CONTINUITY";

export type ExecutionRoute = Exclude<RouteOverride, "AUTO">;

export type JobStatus =
  | "accepted"
  | "queued"
  | "running"
  | "completed"
  | "rejected"
  | "failed"
  | "cancelled"
  | "interrupted";

export const ACTIVE_JOB_STATUSES: readonly JobStatus[] = [
  "accepted",
  "queued",
  "running",
];

export const FAILURE_JOB_STATUSES: readonly JobStatus[] = [
  "rejected",
  "failed",
  "cancelled",
  "interrupted",
];

export function isActiveJobStatus(status: JobStatus): boolean {
  return ACTIVE_JOB_STATUSES.includes(status);
}

export function isFailureJobStatus(status: JobStatus): boolean {
  return FAILURE_JOB_STATUSES.includes(status);
}

export interface EvidenceReference {
  pointer: string;
  url?: string;
}

export interface OutputMetrics {
  tokens: number | null;
  elapsed_seconds: number;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
  route?: ExecutionRoute;
  job_id?: string;
  /**
   * Server outcome for the message that produced this record. A sovereign
   * message with a non-completed terminal status is never rendered as an
   * accepted answer.
   */
  job_status?: JobStatus;
  evidence?: EvidenceReference;
  metrics?: OutputMetrics;
  error?: string;
}

export interface JobProgress {
  percent: number;
  stage?: string;
  detail?: string;
  current?: number;
  total?: number;
}

export interface JobSnapshot {
  job_id: string;
  session_id?: string;
  status: JobStatus;
  route?: ExecutionRoute;
  progress: JobProgress;
  message?: ChatMessage;
  evidence?: EvidenceReference;
  error?: string;
  cancel_requested?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface ChatSession {
  session_id: string;
  created_at: string;
  updated_at: string;
  title: string;
  messages: ChatMessage[];
  active_model_profile: string;
  orchestration_mode: string;
  evidence?: EvidenceReference;
  active_job_id?: string;
  active_job?: JobSnapshot;
  last_job?: JobSnapshot;
}
