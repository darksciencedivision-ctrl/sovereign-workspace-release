import { useEffect, useState } from "react";
import { sovereignClient } from "../services/sovereignClient";
import type { LongRunView, LongTask } from "../types/long";

interface Props {
  jobId: string;
  /** Changes whenever the polled job changes; the view is re-read then (no extra polling). */
  refreshKey: string;
  active: boolean;
}

const MODE_COPY: Record<string, string> = {
  plan_steps: "Plan steps",
  input_shards: "Map/reduce over the material",
};

const TASK_COPY: Record<LongTask["status"], string> = {
  pending: "waiting",
  completed: "done",
  failed: "failed",
};

function LedgerList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="ledger-section">
      <h4>{title}</h4>
      <ul>
        {items.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

/**
 * A LONG run's chunks and the ledger it carries between fresh sessions, read from the run's
 * hash-verified checkpoints (`GET /v1/jobs/<id>/ledger`). Everything shown is model output or
 * run bookkeeping; it is rendered as text, never as markup.
 */
export function LongRunPanel({ jobId, refreshKey, active }: Props) {
  const [run, setRun] = useState<LongRunView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void sovereignClient.getLongRun(jobId).then((result) => {
      if (cancelled) return;
      if (result.ok && result.run) {
        setRun(result.run);
        setError(null);
      } else {
        setError(result.error ?? "The LONG run view is unavailable.");
      }
    });
    return () => {
      cancelled = true;
    };
  }, [jobId, refreshKey]);

  if (!run) {
    return error ? <p className="long-run-note">{error}</p> : null;
  }
  if (!run.started) {
    return (
      <p className="long-run-note">
        The LONG run has not started yet (model load and input sizing come first).
      </p>
    );
  }
  const ledger = run.ledger;
  return (
    <details className="long-run" open={active}>
      <summary>
        {MODE_COPY[run.mode ?? ""] ?? run.mode ?? "LONG run"} - {run.completed ?? 0} of{" "}
        {run.total ?? run.tasks.length} chunks done
        {run.failed ? `, ${run.failed} failed` : ""} - {run.model_calls ?? 0} model calls
      </summary>
      {error && <p className="reconnect-note">{error} Showing the last view read.</p>}
      <ol className="long-tasks" aria-label="Chunks">
        {run.tasks.map((task) => (
          <li key={task.task_id} className={`long-task task-${task.status}`}>
            <span className="long-task-id">{task.task_id}</span>
            <span className="long-task-status">
              {TASK_COPY[task.status]}
              {task.attempts > 1 ? ` after ${task.attempts} attempts` : ""}
            </span>
            {task.summary && <span className="long-task-summary">{task.summary}</span>}
            {task.error && <span className="long-task-error">{task.error}</span>}
          </li>
        ))}
      </ol>
      {ledger && (
        <div className="long-ledger" aria-label="Carried ledger">
          <h3>Ledger carried between chunks</h3>
          <LedgerList title="Facts" items={ledger.facts} />
          <LedgerList title="Decisions" items={ledger.decisions} />
          <LedgerList title="Open questions" items={ledger.open_questions} />
          <LedgerList
            title="Results so far"
            items={ledger.results.map((r) => `${r.task}: ${r.summary}`)}
          />
          {ledger.facts.length + ledger.decisions.length + ledger.open_questions.length +
            ledger.results.length ===
            0 && <p className="long-run-note">Nothing carried yet.</p>}
        </div>
      )}
    </details>
  );
}
