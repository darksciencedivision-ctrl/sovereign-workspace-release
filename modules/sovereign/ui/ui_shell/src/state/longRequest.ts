/**
 * LONG route helpers. Pure functions so the request format and the parsing of the run view are
 * testable without a browser.
 *
 * The server reads a LONG request as: an optional first line `@model: <name>`, the objective,
 * then (for map/reduce) a line `---` followed by the material, or `@input: <file>` naming a file in
 * the state home's `long_inputs` inbox. The operator never types that syntax; the composer builds it.
 */
import type { JobProgress } from "../types/chat";
import type {
  LongLedger,
  LongModelInfo,
  LongOptions,
  LongRouteInfo,
  LongRunView,
  LongTask,
  LongTaskStatus,
} from "../types/long";

/** The product's `/v1/message` input cap (server MAX_INPUT_CHARACTERS). */
export const MAX_INPUT_CHARACTERS = 131_072;
/** Same rule the server applies to `@input:` names. */
const INBOX_NAME = /^[A-Za-z0-9._ -]{1,128}$/;

export type ComposeResult = { ok: true; text: string } | { ok: false; error: string };

export function composeLongRequest(objective: string, options: LongOptions): ComposeResult {
  const goal = objective.trim();
  if (!goal) return { ok: false, error: "Write the objective for the LONG run." };
  if (/^---[ \t]*$/m.test(goal)) {
    return { ok: false, error: "The objective cannot contain a line of only '---'." };
  }
  const lines: string[] = [];
  if (options.model.trim()) lines.push(`@model: ${options.model.trim()}`);
  lines.push(goal);
  if (options.mode === "material") {
    const material = options.material.replace(/^\s*\n/, "").replace(/\s+$/, "");
    if (!material.trim()) {
      return { ok: false, error: "Paste the material to work through, or choose plan steps." };
    }
    lines.push("---", material);
  } else if (options.mode === "inbox") {
    const name = options.inboxFile.trim();
    if (!INBOX_NAME.test(name)) {
      return {
        ok: false,
        error: "Name a plain file in the long_inputs inbox (letters, digits, space, . _ -).",
      };
    }
    lines.push("---", `@input: ${name}`);
  }
  const text = lines.join("\n");
  if (text.length > MAX_INPUT_CHARACTERS) {
    return {
      ok: false,
      error:
        `The request is ${text.length.toLocaleString()} characters; the limit is ` +
        `${MAX_INPUT_CHARACTERS.toLocaleString()}. Put large material in the long_inputs ` +
        "inbox and reference the file instead.",
    };
  }
  return { ok: true, text };
}

/** "Chunk 3 of 7" while a sharded run reports its task counts. */
export function chunkLabel(progress: JobProgress | undefined): string | undefined {
  if (!progress) return undefined;
  const { current, total } = progress;
  if (typeof current !== "number" || typeof total !== "number" || total <= 0) return undefined;
  const shown = Math.min(Math.max(0, Math.floor(current)), Math.floor(total));
  return `${shown} of ${Math.floor(total)} chunks done`;
}

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

function count(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function text(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

export function normalizeLongRoute(
  ready: unknown,
  raw: unknown
): LongRouteInfo | undefined {
  if (ready === undefined && raw === undefined) return undefined;
  const info = isRecord(raw) ? raw : {};
  const models: LongModelInfo[] = Array.isArray(info.models)
    ? info.models.flatMap((m) =>
        isRecord(m) && typeof m.model === "string"
          ? [{
              model: m.model,
              context: count(m.context) ?? 0,
              thinking: text(m.thinking) ?? "off",
            }]
          : []
      )
    : [];
  return {
    ready: ready === true,
    defaultModel: text(info.default_model),
    models,
    error: text(info.error),
  };
}

const TASK_STATUSES: LongTaskStatus[] = ["pending", "completed", "failed", "split"];

export function normalizeLongRun(raw: unknown, jobId: string): LongRunView | null {
  if (!isRecord(raw)) return null;
  const tasks: LongTask[] = Array.isArray(raw.tasks)
    ? raw.tasks.flatMap((t) => {
        if (!isRecord(t) || typeof t.task_id !== "string") return [];
        const status = TASK_STATUSES.includes(t.status as LongTaskStatus)
          ? (t.status as LongTaskStatus)
          : "pending";
        return [{
          task_id: t.task_id,
          kind: text(t.kind) ?? "",
          status,
          attempts: count(t.attempts) ?? 0,
          summary: text(t.summary) ?? null,
          error: text(t.error) ?? null,
          utc: text(t.utc) ?? null,
        }];
      })
    : [];
  let ledger: LongLedger | null = null;
  if (isRecord(raw.ledger)) {
    ledger = {
      facts: strings(raw.ledger.facts),
      decisions: strings(raw.ledger.decisions),
      open_questions: strings(raw.ledger.open_questions),
      results: Array.isArray(raw.ledger.results)
        ? raw.ledger.results.flatMap((r) =>
            isRecord(r) && typeof r.summary === "string"
              ? [{ task: text(r.task) ?? "", summary: r.summary }]
              : []
          )
        : [],
    };
  }
  return {
    job_id: text(raw.job_id) ?? jobId,
    started: raw.started === true,
    job_status: text(raw.job_status),
    mode: text(raw.mode),
    objective: text(raw.objective),
    run_status: text(raw.run_status),
    model_calls: count(raw.model_calls),
    completed: count(raw.completed),
    failed: count(raw.failed),
    total: count(raw.total),
    tasks,
    ledger,
  };
}

export const EMPTY_LONG_OPTIONS: LongOptions = {
  model: "",
  mode: "plan",
  material: "",
  inboxFile: "",
};
