/**
 * Validation Lab state — Phase UI-7.
 * All engine interaction goes through sovereignClient. Nothing here
 * fabricates results: status, errors, and result lists come from the
 * client verbatim.
 */
import { useCallback, useEffect, useState } from "react";
import type { ValidationResult, ValidationStatus } from "../types/validation";
import { sovereignClient } from "../services/sovereignClient";

export function useValidationState(open: boolean) {
  const [status, setStatus] = useState<ValidationStatus | null>(null);
  const [results, setResults] = useState<ValidationResult[]>([]);
  const [running, setRunning] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    Promise.all([
      sovereignClient.getValidationStatus(),
      sovereignClient.getValidationResults(),
    ]).then(([st, res]) => {
      if (cancelled) return;
      setStatus(st);
      setResults(res);
    });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const run = useCallback(
    async (topic: string, kind: "benchmark" | "comparison") => {
      if (running) return;
      setRunning(true);
      setLastError(null);
      try {
        const r = await sovereignClient.runBenchmark(topic, kind);
        if (!r.ok) {
          setLastError(r.error ?? "Validation module not connected.");
          return;
        }
        setResults(await sovereignClient.getValidationResults());
      } finally {
        setRunning(false);
      }
    },
    [running]
  );

  const exportEvidence = useCallback(async () => {
    setLastError(null);
    const r = await sovereignClient.exportEvidence();
    if (!r.ok) setLastError(r.error ?? "Validation module not connected.");
  }, []);

  return { status, results, running, lastError, run, exportEvidence };
}
