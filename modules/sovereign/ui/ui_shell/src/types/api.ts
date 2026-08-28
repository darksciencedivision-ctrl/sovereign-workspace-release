/**
 * Canonical product API wire types. Runtime normalization remains deliberately
 * tolerant of bare records and `{session|sessions|job|models|profile}` envelopes
 * so compatible server revisions do not turn into misleading empty screens.
 */
import type {
  ChatMessage,
  ChatSession,
  ExecutionRoute,
  JobProgress,
  JobSnapshot,
  JobStatus,
  RouteOverride,
} from "./chat";
import type { ModelInfo, ModelProfile } from "./model";
import type { Settings } from "./settings";

export interface ApiMessageRequest {
  input: string;
  session_id: string;
  route_override: RouteOverride;
}

export interface ApiMessageResponse {
  ok?: boolean;
  job_id?: string;
  status?: JobStatus;
  route?: ExecutionRoute;
  progress?: number | Partial<JobProgress>;
  message?: ChatMessage;
  evidence_pointer?: string;
  evidence_url?: string;
  evidence_log_path?: string;
  error?: string;
  job?: JobSnapshot;
}

export interface ApiOkResponse {
  ok?: boolean;
  error?: string;
}

export interface ApiHealthResponse {
  status?: string;
  ok?: boolean;
  engine_version?: string;
  product_version?: string;
  version?: string;
  orchestration_mode?: string;
  mode?: string;
  detail?: string;
}

export type ApiModelsResponse =
  | ModelInfo[]
  | { models: ModelInfo[] };
export type ApiModelProfileResponse =
  | ModelProfile
  | { profile: ModelProfile };
export type ApiSessionsResponse =
  | ChatSession[]
  | { sessions: ChatSession[] };
export type ApiSessionResponse =
  | ChatSession
  | { session: ChatSession };
export type ApiSettingsResponse =
  | Settings
  | { settings: Settings };

export interface EngineHealth {
  reachable: boolean;
  status?: string;
  engineVersion?: string;
  orchestrationMode?: string;
  detail?: string;
}
