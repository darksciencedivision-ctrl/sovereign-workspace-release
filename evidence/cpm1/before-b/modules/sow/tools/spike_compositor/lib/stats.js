"use strict";
/** Latency statistics. Timeout-censored samples are counted, not silently dropped. */
function percentile(sorted, p) {
  if (sorted.length === 0) return null;
  const idx = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[Math.max(0, idx)];
}
function latencyStats(samplesMs, timeouts = 0) {
  const sorted = [...samplesMs].sort((a, b) => a - b);
  return {
    n: sorted.length,
    timeouts,
    min: sorted[0] ?? null,
    p50: percentile(sorted, 50),
    p95: percentile(sorted, 95),
    p99: percentile(sorted, 99),
    max: sorted[sorted.length - 1] ?? null,
    mean: sorted.length ? sorted.reduce((s, x) => s + x, 0) / sorted.length : null,
  };
}
module.exports = { percentile, latencyStats };
