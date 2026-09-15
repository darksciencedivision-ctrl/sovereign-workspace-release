import type {
  ApiHealthResponse,
  ApiMessageResponse,
  ApiModelProfileResponse,
  ApiModelsResponse,
  ApiOkResponse,
  ApiSessionResponse,
  ApiSessionsResponse,
  ApiSettingsResponse,
  EngineHealth,
} from "../types/api";
import {
  FAILURE_JOB_STATUSES,
  type ChatMessage,
  type ChatSession,
  type EvidenceReference,
  type ExecutionRoute,
  type JobProgress,
  type JobSnapshot,
  type JobStatus,
  type RouteOverride,
} from "../types/chat";
import type {
  ModelInfo,
  ModelProfile,
  RoleAssignment,
} from "../types/model";
import type { Settings } from "../types/settings";
import type { ValidationResult, ValidationStatus } from "../types/validation";
import {
  ERR_NOT_REACHABLE,
  ERR_VALIDATION,
  type JobResult,
  type ModelAssignmentResult,
  type OkResult,
  type SessionResult,
  type SessionsResult,
  type SubmissionResult,
  type SovereignTransport,
} from "./transport";

const REQUEST_TIMEOUT_MS = 20_000;
const HEALTH_TIMEOUT_MS = 4_000;

type JsonRecord = Record<string, unknown>;

interface HttpFailure {
  ok: false;
  error: string;
  status: number;
  data?: unknown;
}

type HttpResult<T> = { ok: true; data: T; status: number } | HttpFailure;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function firstString(...values: unknown[]): string | undefined {
  return values.find((value): value is string => typeof value === "string");
}

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function normalizeRoute(value: unknown): ExecutionRoute | undefined {
  if (typeof value !== "string") return undefined;
  const route = value.toUpperCase();
  return ["STATUS", "QUICK", "DEEP", "RESEARCH", "CONTINUITY"].includes(route)
    ? (route as ExecutionRoute)
    : undefined;
}

function normalizeStatus(value: unknown): JobStatus | undefined {
  if (typeof value !== "string") return undefined;
  const status = value.toLowerCase();
  if (status === "concurrence_not_reached") return "rejected";
  if (status === "timeout") return "failed";
  if (status === "canceled") return "cancelled";
  return [
    "accepted",
    "queued",
    "running",
    "completed",
    "rejected",
    "failed",
    "cancelled",
    "interrupted",
  ].includes(status)
    ? (status as JobStatus)
    : undefined;
}

function normalizeEvidence(record: JsonRecord): EvidenceReference | undefined {
  const nested = isRecord(record.evidence) ? record.evidence : undefined;
  const pointer = firstString(
    record.evidence_pointer,
    record.evidence_log_path,
    record.evidence_path,
    nested?.pointer,
    nested?.evidence_pointer
  );
  if (!pointer) return undefined;
  return {
    pointer,
    url: firstString(record.evidence_url, nested?.url, nested?.evidence_url),
  };
}

function normalizeProgress(
  value: unknown,
  status: JobStatus
): JobProgress {
  if (typeof value === "number" && Number.isFinite(value)) {
    return { percent: clampPercent(value) };
  }
  if (isRecord(value)) {
    const current =
      typeof value.current === "number" && Number.isFinite(value.current)
        ? value.current
        : undefined;
    const total =
      typeof value.total === "number" && Number.isFinite(value.total)
        ? value.total
        : undefined;
    const rawPercent =
      typeof value.percent === "number"
        ? value.percent
        : typeof value.percentage === "number"
          ? value.percentage
          : current !== undefined && total !== undefined && total > 0
            ? (current / total) * 100
            : undefined;
    return {
      percent:
        rawPercent === undefined
          ? status === "completed"
            ? 100
            : 0
          : clampPercent(rawPercent),
      stage: firstString(value.stage, value.phase),
      detail: firstString(value.detail, value.message),
      current,
      total,
    };
  }
  return { percent: status === "completed" ? 100 : 0 };
}

function normalizeMessage(value: unknown): ChatMessage | undefined {
  if (!isRecord(value)) return undefined;
  const content = firstString(value.content, value.text, value.output);
  const rawRole = firstString(value.role);
  if (content === undefined || rawRole === undefined) return undefined;
  const role =
    rawRole.toLowerCase() === "user"
      ? "user"
      : ["assistant", "sovereign"].includes(rawRole.toLowerCase())
        ? "sovereign"
        : undefined;
  if (!role) return undefined;
  const status = normalizeStatus(value.job_status ?? value.status);
  return {
    id: firstString(value.id, value.message_id) ?? crypto.randomUUID(),
    role,
    content,
    timestamp:
      firstString(value.timestamp, value.created_at) ??
      new Date().toISOString(),
    route: normalizeRoute(value.route),
    job_id: firstString(value.job_id),
    job_status: status,
    evidence: normalizeEvidence(value),
    metrics: normalizeOutputMetrics(value.metrics),
    error: firstString(value.error),
  };
}

function normalizeOutputMetrics(value: unknown): ChatMessage["metrics"] {
  if (!isRecord(value)) return undefined;
  const elapsed = value.elapsed_seconds;
  if (
    typeof elapsed !== "number" ||
    !Number.isFinite(elapsed) ||
    elapsed < 0
  ) {
    return undefined;
  }
  const rawTokens = value.tokens;
  const tokens =
    typeof rawTokens === "number" &&
    Number.isSafeInteger(rawTokens) &&
    rawTokens >= 0
      ? rawTokens
      : null;
  return { tokens, elapsed_seconds: elapsed };
}

function normalizeJob(
  value: unknown,
  fallbackId?: string
): JobSnapshot | undefined {
  if (!isRecord(value)) return undefined;
  const nested = isRecord(value.job) ? value.job : undefined;
  const record = nested ? { ...value, ...nested } : value;
  const message = normalizeMessage(record.message);
  const status =
    normalizeStatus(record.status) ?? (message ? "completed" : undefined);
  const jobId = firstString(record.job_id, record.id, fallbackId);
  if (!status || !jobId) return undefined;
  const evidence = normalizeEvidence(record) ?? message?.evidence;
  return {
    job_id: jobId,
    session_id: firstString(record.session_id),
    status,
    route: normalizeRoute(record.route),
    progress: normalizeProgress(record.progress, status),
    message:
      status === "completed" && message
        ? { ...message, job_id: jobId, job_status: status, evidence }
        : undefined,
    evidence,
    error: firstString(record.error, record.detail),
    cancel_requested: record.cancel_requested === true,
    created_at: firstString(record.created_at),
    updated_at: firstString(record.updated_at),
  };
}

function normalizeSession(value: unknown): ChatSession | undefined {
  if (!isRecord(value)) return undefined;
  const nested = isRecord(value.session) ? value.session : undefined;
  const record = nested ?? value;
  const sessionId = firstString(record.session_id, record.id);
  if (!sessionId) return undefined;
  const activeJob = normalizeJob(record.active_job);
  const lastJob = normalizeJob(record.last_job);
  const rawMessages = Array.isArray(record.messages) ? record.messages : [];
  const messages = rawMessages
    .map(normalizeMessage)
    .filter((message): message is ChatMessage => message !== undefined)
    .map((message) => {
      const related =
        message.job_id === activeJob?.job_id
          ? activeJob
          : message.job_id === lastJob?.job_id
            ? lastJob
            : undefined;
      return related && message.role === "sovereign"
        ? {
            ...message,
            job_status: related.status,
            error: message.error ?? related.error,
          }
        : message;
    });
  const createdAt =
    firstString(record.created_at) ?? new Date(0).toISOString();
  return {
    session_id: sessionId,
    created_at: createdAt,
    updated_at: firstString(record.updated_at) ?? createdAt,
    title: firstString(record.title) ?? "Untitled session",
    messages,
    active_model_profile:
      firstString(record.active_model_profile, record.model_profile) ??
      "default",
    orchestration_mode:
      firstString(record.orchestration_mode, record.mode) ?? "AUTO",
    evidence: normalizeEvidence(record),
    active_job_id:
      firstString(record.active_job_id, record.current_job_id) ??
      activeJob?.job_id,
    active_job: activeJob,
    last_job: lastJob,
  };
}

function extractError(data: unknown, fallback: string): string {
  if (!isRecord(data)) return fallback;
  return firstString(data.error, data.detail) ?? fallback;
}

async function request<T>(
  baseUrl: string,
  method: "GET" | "POST" | "PUT",
  path: string,
  body?: unknown,
  timeoutMs: number = REQUEST_TIMEOUT_MS
): Promise<HttpResult<T>> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      method,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        ...(body !== undefined
          ? { "Content-Type": "application/json" }
          : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    const text = await response.text();
    let data: unknown = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (error) {
        console.error(`httpTransport: malformed JSON from ${path}`, error);
        return {
          ok: false,
          error: response.ok
            ? "Sovereign returned an invalid response."
            : ERR_NOT_REACHABLE,
          status: response.status,
        };
      }
    }
    if (!response.ok) {
      return {
        ok: false,
        error: extractError(data, `Sovereign request failed (HTTP ${response.status}).`),
        status: response.status,
        data,
      };
    }
    return { ok: true, data: data as T, status: response.status };
  } catch (error) {
    console.error(`httpTransport: ${method} ${path} failed`, error);
    return { ok: false, error: ERR_NOT_REACHABLE, status: 0 };
  } finally {
    window.clearTimeout(timer);
  }
}

function sessionResult(result: HttpResult<ApiSessionResponse>): SessionResult {
  if (!result.ok) return { ok: false, error: result.error };
  const session = normalizeSession(result.data);
  return session
    ? { ok: true, session }
    : { ok: false, error: "Sovereign returned an invalid session record." };
}


export function normalizeSubmissionResult(
  result: HttpResult<ApiMessageResponse>
): SubmissionResult {
  if (!result.ok) {
    const rejectedJob = normalizeJob(result.data, `rejected-${Date.now()}`);
    return {
      ok: false,
      status: rejectedJob?.status,
      route: rejectedJob?.route,
      job: rejectedJob,
      error: rejectedJob?.error ?? result.error,
    };
  }

  const record = isRecord(result.data) ? result.data : {};
  const job = normalizeJob(record, firstString(record.job_id));
  const directMessage = normalizeMessage(record.message);
  const status =
    normalizeStatus(record.status) ??
    job?.status ??
    (directMessage ? "completed" : undefined);
  const route = normalizeRoute(record.route) ?? job?.route;
  const failure = status ? FAILURE_JOB_STATUSES.includes(status) : false;

  if (job && job.status !== "completed") {
    return {
      ok: !failure,
      status: job.status,
      route,
      job,
      error: failure
        ? job.error ?? extractError(record, `Run ${job.status}.`)
        : undefined,
    };
  }

  const completedMessage = job?.message ?? directMessage;
  if (status === "completed" && completedMessage) {
    return {
      ok: true,
      status,
      route,
      message: {
        ...completedMessage,
        route: completedMessage.route ?? route,
        job_status: "completed",
        evidence:
          completedMessage.evidence ??
          job?.evidence ??
          normalizeEvidence(record),
      },
      job,
    };
  }

  return {
    ok: false,
    status,
    route,
    job,
    error: extractError(record, "Sovereign did not accept the request."),
  };
}

export function createHttpTransport(baseUrl = ""): SovereignTransport {
  return {
    async sendMessage(
      input: string,
      sessionId: string,
      routeOverride: RouteOverride
    ): Promise<SubmissionResult> {
      const result = await request<ApiMessageResponse>(
        baseUrl,
        "POST",
        "/v1/message",
        {
          input,
          session_id: sessionId,
          route_override: routeOverride,
        }
      );

      return normalizeSubmissionResult(result);
    },

    async getJob(jobId: string): Promise<JobResult> {
      const result = await request<unknown>(
        baseUrl,
        "GET",
        `/v1/jobs/${encodeURIComponent(jobId)}`
      );
      if (!result.ok) return { ok: false, error: result.error };
      const job = normalizeJob(result.data, jobId);
      return job
        ? { ok: true, job }
        : { ok: false, error: "Sovereign returned an invalid job record." };
    },

    async cancelJob(jobId: string): Promise<JobResult> {
      const result = await request<unknown>(
        baseUrl,
        "POST",
        `/v1/jobs/${encodeURIComponent(jobId)}/cancel`,
        {}
      );
      if (!result.ok) {
        const job = normalizeJob(result.data, jobId);
        return { ok: false, job, error: result.error };
      }
      const job = normalizeJob(result.data, jobId);
      return job
        ? { ok: true, job }
        : { ok: false, error: "Sovereign returned an invalid cancellation response." };
    },

    async createSession(): Promise<SessionResult> {
      return sessionResult(
        await request<ApiSessionResponse>(
          baseUrl,
          "POST",
          "/v1/sessions",
          {}
        )
      );
    },

    async getChatHistory(): Promise<SessionsResult> {
      const result = await request<ApiSessionsResponse>(
        baseUrl,
        "GET",
        "/v1/sessions"
      );
      if (!result.ok) {
        return { ok: false, sessions: [], error: result.error };
      }
      const source = Array.isArray(result.data)
        ? result.data
        : isRecord(result.data) && Array.isArray(result.data.sessions)
          ? result.data.sessions
          : null;
      if (!source) {
        return {
          ok: false,
          sessions: [],
          error: "Sovereign returned an invalid session list.",
        };
      }
      return {
        ok: true,
        sessions: source
          .map(normalizeSession)
          .filter((session): session is ChatSession => session !== undefined),
      };
    },

    async loadSession(sessionId: string): Promise<SessionResult> {
      return sessionResult(
        await request<ApiSessionResponse>(
          baseUrl,
          "GET",
          `/v1/sessions/${encodeURIComponent(sessionId)}`
        )
      );
    },

    async getModels(): Promise<ModelInfo[]> {
      const result = await request<ApiModelsResponse>(
        baseUrl,
        "GET",
        "/v1/models"
      );
      if (!result.ok) return [];
      if (Array.isArray(result.data)) return result.data;
      return isRecord(result.data) && Array.isArray(result.data.models)
        ? (result.data.models as ModelInfo[])
        : [];
    },

    async getModelProfile(): Promise<ModelProfile> {
      const result = await request<ApiModelProfileResponse>(
        baseUrl,
        "GET",
        "/v1/models/profile"
      );
      if (!result.ok || !isRecord(result.data)) {
        return { name: "unavailable", assignments: [] };
      }
      const source: JsonRecord = isRecord(result.data.profile)
        ? result.data.profile
        : (result.data as JsonRecord);
      return typeof source.name === "string" &&
        Array.isArray(source.assignments)
        ? (source as unknown as ModelProfile)
        : { name: "unavailable", assignments: [] };
    },

    async setModelAssignments(
      assignments: RoleAssignment[]
    ): Promise<ModelAssignmentResult> {
      const result = await request<ApiOkResponse & ApiModelProfileResponse>(
        baseUrl,
        "POST",
        "/v1/models/active",
        { assignments }
      );
      if (!result.ok) return { ok: false, error: result.error };
      const record: JsonRecord = isRecord(result.data) ? result.data : {};
      const profile = isRecord(record.profile)
        ? (record.profile as unknown as ModelProfile)
        : undefined;
      return {
        ok: record.ok !== false && profile !== undefined,
        error: firstString(record.error),
        profile,
      };
    },

    async getSettings(): Promise<Settings | null> {
      const result = await request<ApiSettingsResponse>(
        baseUrl,
        "GET",
        "/v1/settings"
      );
      if (!result.ok || !isRecord(result.data)) return null;
      const source = isRecord(result.data.settings)
        ? result.data.settings
        : result.data;
      return source as unknown as Settings;
    },

    async updateSettings(settings: Settings): Promise<OkResult> {
      const result = await request<ApiOkResponse>(
        baseUrl,
        "PUT",
        "/v1/settings",
        settings
      );
      if (!result.ok) return { ok: false, error: result.error };
      return {
        ok: result.data.ok !== false,
        error: result.data.error,
      };
    },

    async health(): Promise<EngineHealth> {
      const result = await request<ApiHealthResponse>(
        baseUrl,
        "GET",
        "/v1/health",
        undefined,
        HEALTH_TIMEOUT_MS
      );
      if (!result.ok) return { reachable: false, detail: result.error };
      return {
        reachable: true,
        status: firstString(result.data.status) ?? "ok",
        engineVersion: firstString(
          result.data.product_version,
          result.data.engine_version,
          result.data.version
        ),
        orchestrationMode: firstString(
          result.data.orchestration_mode,
          result.data.mode
        ),
        detail: firstString(result.data.detail),
      };
    },

    async getValidationStatus(): Promise<ValidationStatus> {
      const result = await request<ValidationStatus>(
        baseUrl,
        "GET",
        "/v1/validation/status"
      );
      return result.ok
        ? result.data
        : { connected: false, detail: ERR_VALIDATION };
    },

    async runBenchmark(
      topic: string,
      kind: "benchmark" | "comparison"
    ): Promise<OkResult> {
      const result = await request<ApiOkResponse>(
        baseUrl,
        "POST",
        "/v1/validation/benchmark",
        { topic, kind }
      );
      if (!result.ok) return { ok: false, error: ERR_VALIDATION };
      return {
        ok: result.data.ok !== false,
        error: result.data.error,
      };
    },

    async getValidationResults(): Promise<ValidationResult[]> {
      const result = await request<ValidationResult[]>(
        baseUrl,
        "GET",
        "/v1/validation/results"
      );
      return result.ok && Array.isArray(result.data) ? result.data : [];
    },

    async exportEvidence(): Promise<OkResult> {
      const result = await request<ApiOkResponse>(
        baseUrl,
        "POST",
        "/v1/validation/export",
        {}
      );
      if (!result.ok) return { ok: false, error: ERR_VALIDATION };
      return {
        ok: result.data.ok !== false,
        error: result.data.error,
      };
    },
  };
}
