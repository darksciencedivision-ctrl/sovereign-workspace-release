import {
  isActiveJobStatus,
  isFailureJobStatus,
  type JobSnapshot,
} from "../types/chat";
import { EvidenceLink } from "./EvidenceLink";

interface Props {
  job: JobSnapshot | null;
  pollError?: string | null;
  cancelling?: boolean;
  onCancel: () => void;
}

const STATUS_COPY: Record<JobSnapshot["status"], string> = {
  accepted: "Accepted",
  queued: "Queued",
  running: "Running",
  completed: "Completed",
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

  return (
    <section
      className={`run-status status-${job.status}`}
      aria-label="Current run"
      aria-live="polite"
      role={failure ? "alert" : "status"}
    >
      <div className="run-status-heading">
        <div>
          <span className={`status-chip ${failure ? "failure" : ""}`}>
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
            <span>{progressLabel}</span>
          </div>
        </>
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
