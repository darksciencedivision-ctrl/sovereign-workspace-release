import { useState } from "react";
import { useValidationState } from "../state/validationState";

/**
 * Validation Lab — Phase UI-7. Advanced-only, per directive.
 * Never renders fabricated results. When the validation module is not
 * connected, every action reports that truthfully.
 */
export function ValidationLab() {
  const [open, setOpen] = useState(false);
  const [topic, setTopic] = useState("");
  const { status, results, running, lastError, run, exportEvidence } =
    useValidationState(open);

  return (
    <div className="group">
      <button
        className="toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? "Hide Validation Lab" : "Validation Lab (advanced)"}
      </button>

      {open && (
        <>
          <div className="row">
            <span>Module status</span>
            <span className="muted">
              {status === null
                ? "Checking…"
                : status.connected
                  ? "Connected"
                  : (status.detail ?? "Validation module not connected.")}
            </span>
          </div>

          <div className="row">
            <span>Benchmark topic</span>
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="Topic to benchmark"
              aria-label="Benchmark topic"
            />
          </div>

          <div className="row">
            <span>Run benchmark</span>
            <button
              className="toggle"
              disabled={running || !topic.trim()}
              onClick={() => run(topic.trim(), "benchmark")}
            >
              {running ? "Running…" : "Run"}
            </button>
          </div>

          <div className="row">
            <span>Compare direct model vs Sovereign</span>
            <button
              className="toggle"
              disabled={running || !topic.trim()}
              onClick={() => run(topic.trim(), "comparison")}
            >
              {running ? "Running…" : "Compare"}
            </button>
          </div>

          <div className="row">
            <span>Export evidence packet</span>
            <button className="toggle" disabled={running} onClick={exportEvidence}>
              Export
            </button>
          </div>

          {lastError && <div className="placeholder-note">{lastError}</div>}

          <div className="group-title" style={{ marginTop: 12 }}>
            Previous results
          </div>
          {results.length === 0 ? (
            <div className="placeholder-note">
              No validation results. Results appear here only after real
              validation runs complete.
            </div>
          ) : (
            results.map((r) => (
              <div className="row" key={r.id}>
                <span>
                  {r.kind}: {r.topic.slice(0, 30)}
                </span>
                <span className="muted">{r.summary}</span>
              </div>
            ))
          )}
        </>
      )}
    </div>
  );
}
