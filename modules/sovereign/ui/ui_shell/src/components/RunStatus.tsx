import {
  isActiveJobStatus,
  isFailureJobStatus,
  type JobSnapshot,
} from "../types/chat";
import { chunkLabel } from "../state/longRequest";
import { EvidenceLink } from "./EvidenceLink";
import { LongRunPanel } from "./LongRunPanel";

interface Props {
  job: JobSnapshot | null;
  pollError?: string | null;
  cancelling?: boolean;
  onCancel: () => void;
}

// SWS-CORRECTIVE-01 §7.1. "Accepted" named a bare verdict, and a reader could reasonably
// take it to mean the answer had been checked for truth. It has not been. The acceptance
// gate checks three things - the answer's format, that every citation it prints exists in
// the evidence packet, and that every clause asserting a project fact either carries a
// citation or is itself an abstention. It does NOT read the cited source to see whether it
// supports the claim, and it does not judge factual accuracy. The label says which of those
// it means, and the title attribute carries the rest.
// F-123: the server reports an accepted answer as status "completed" (it never emits "accepted"),
// so the careful acceptance-check copy and its tooltip attach to "completed" - otherwise they were
// unreachable. "accepted" is retained for any caller that still uses it.
const STATUS_COPY: Record<JobSnapshot["status"], string> = {
  accepted: "Accepted — format and citations checked",
  queued: "Queued",
  running: "Running",
  completed: "Completed — format and citations checked",
  rejected: "Rejected — no answer accepted",
  failed: "Failed — no answer accepted",
  cancelled: "Cancelled — no answer accepted",
  interrupted: "Interrupted — no answer accepted",
};

export function RunStatus({
  job,
  pollError,
  cancelling,
  onCancel,
}: Props) {
  if (!job) return null;
  const active = isActiveJobStatus(job.status);
  const failure = isFailureJobStatus(job.status);
  const progressLabel = `${job.progress.percent}%`;
  const chunks = chunkLabel(job.progress);

  return (
    <section
      className={`run-status status-${job.status}`}
      aria-label="Current run"
      aria-live="polite"
      role={failure ? "alert" : "status"}
    >
      <div className="run-status-heading">
        <div>
          <span
            className={`status-chip ${failure ? "failure" : ""}`}
            title={
              job.status === "accepted" || job.status === "completed"
                ? "Checked: response format, that every printed citation exists in the " +
                  "evidence packet, and that every project-fact claim is cited or is an " +
                  "abstention. NOT checked: whether a cited source actually supports the " +
                  "claim, and whether the answer is factually correct."
                : undefined
            }
          >
            {STATUS_COPY[job.status]}
          </span>
          {job.route && <span className="route-chip">{job.route}</span>}
        </div>
        <div className="run-actions">
          <EvidenceLink evidence={job.evidence} />
          {active && (
            <button
              type="button"
              className="cancel-run"
              onClick={onCancel}
              disabled={cancelling || job.cancel_requested}
            >
              {cancelling || job.cancel_requested
                ? "Cancellation requested…"
                : "Cancel"}
            </button>
          )}
        </div>
      </div>

      {active && (
        <>
          <div
            className="progress-track"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={job.progress.percent}
            aria-label="Run progress"
          >
            <div
              className="progress-fill"
              style={{ width: progressLabel }}
            />
          </div>
          <div className="run-detail">
            <span>
              {job.progress.stage ?? "Waiting for progress"}
              {job.progress.detail ? ` — ${job.progress.detail}` : ""}
            </span>
            <span>{chunks ? `${chunks} - ${progressLabel}` : progressLabel}</span>
          </div>
        </>
      )}

      {job.route === "LONG" && (
        <LongRunPanel
          jobId={job.job_id}
          refreshKey={`${job.status}|${job.updated_at ?? ""}|${job.progress.current ?? ""}|${job.progress.total ?? ""}`}
          active={active}
        />
      )}

      {failure && (
        <p className="run-error">
          {job.error ??
            "Sovereign did not produce an accepted answer for this run."}
        </p>
      )}
      {pollError && (
        <p className="reconnect-note">
          {pollError} The run remains server-owned and this view will retry.
        </p>
      )}
      <details className="run-identity">
        <summary>Run identity</summary>
        <code>{job.job_id}</code>
        {job.evidence && <code>{job.evidence.pointer}</code>}
      </details>
    </section>
  );
}
