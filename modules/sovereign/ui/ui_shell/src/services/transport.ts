import type {
  ChatMessage,
  ChatSession,
  ExecutionRoute,
  JobSnapshot,
  JobStatus,
  RouteOverride,
} from "../types/chat";
import type { ModelInfo, ModelProfile, RoleAssignment } from "../types/model";
import type { Settings } from "../types/settings";
import type { EngineHealth } from "../types/api";
import type { LongRunView } from "../types/long";
import type { ValidationResult, ValidationStatus } from "../types/validation";

export interface SubmissionResult {
  ok: boolean;
  status?: JobStatus;
  route?: ExecutionRoute;
  message?: ChatMessage;
  job?: JobSnapshot;
  error?: string;
}

export interface JobResult {
  ok: boolean;
  job?: JobSnapshot;
  error?: string;
}

export interface LongRunResult {
  ok: boolean;
  run?: LongRunView;
  error?: string;
}

export interface SessionResult {
  ok: boolean;
  session?: ChatSession;
  error?: string;
}

export interface SessionsResult {
  ok: boolean;
  sessions: ChatSession[];
  error?: string;
}

export interface OkResult {
  ok: boolean;
  error?: string;
}

export interface ModelAssignmentResult extends OkResult {
  profile?: ModelProfile;
}

export interface SovereignTransport {
  sendMessage(
    input: string,
    sessionId: string,
    routeOverride: RouteOverride
  ): Promise<SubmissionResult>;
  getJob(jobId: string): Promise<JobResult>;
  cancelJob(jobId: string): Promise<JobResult>;
  /** LONG jobs only: chunks and the carried ledger, read from the run's checkpoints. */
  getLongRun(jobId: string): Promise<LongRunResult>;
  createSession(): Promise<SessionResult>;
  getChatHistory(): Promise<SessionsResult>;
  loadSession(sessionId: string): Promise<SessionResult>;
  getModels(): Promise<ModelInfo[]>;
  getModelProfile(): Promise<ModelProfile>;
  setModelAssignments(
    assignments: RoleAssignment[]
  ): Promise<ModelAssignmentResult>;
  getSettings(): Promise<Settings | null>;
  updateSettings(settings: Settings): Promise<OkResult>;
  health(): Promise<EngineHealth>;
  getValidationStatus(): Promise<ValidationStatus>;
  runBenchmark(topic: string, kind: "benchmark" | "comparison"): Promise<OkResult>;
  getValidationResults(): Promise<ValidationResult[]>;
  exportEvidence(): Promise<OkResult>;
}

export const ERR_NOT_REACHABLE = "Sovereign engine is not reachable.";
export const ERR_MODEL_UNAVAILABLE = "Selected model is unavailable.";
export const ERR_API_KEY = "API key required for this provider.";
export const ERR_VALIDATION = "Validation module not connected.";
