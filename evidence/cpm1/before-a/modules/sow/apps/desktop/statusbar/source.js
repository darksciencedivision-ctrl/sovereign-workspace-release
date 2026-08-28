"use strict";
/**
 * Status-bar data SOURCE — reads the live subscription-concurrency count over the D-IPC-01 channel
 * (phase-15a.statusbar). This is the read-only glue the §11/15A status bar rides.
 *
 * It uses the SAME authenticated loopback IpcClient the shell already proves against the Python
 * gateway (apps/desktop/ipc/client.js, mirroring control_plane/ipc/client.py), calls the ONE
 * read-only op the SubscriptionStatusControlSurface exposes — `subscription_status` — and folds the
 * governor's `status()` dict through the pure view model (terminal/statusbar/statusbar-model). It
 * renders nothing and holds no policy; the governor OWNS every concurrency decision.
 *
 * READ-ONLY, by the surface it talks to: SubscriptionStatusControlSurface answers only
 * {health, subscription_status} and cannot register/acquire/release or raise an allowance. So this
 * path carries no authority and needs no write-credential broker.
 *
 * TWO entry points, matching the inspector source's split:
 *   - fetchSubscriptionStatus(client)  — STRICT: throws StatusBarSourceError on an ok:false payload
 *     and PROPAGATES transport faults, so fail-closed behaviour is directly testable.
 *   - fetchStatusBarModel(client, opts) — DISPLAY: always returns a model. On any fault it returns a
 *     fail-closed `readable:false` model (unknown rows, no fabricated count) carrying `.error`, so
 *     the always-visible status bar renders honestly rather than throwing into the renderer.
 */
const { buildStatusBarModel, summarizeStatusBar } = require("../../../terminal/statusbar/statusbar-model");

class StatusBarSourceError extends Error {}

/**
 * Read the governor status once over IPC. STRICT + fail-closed: an ok:false payload throws with the
 * surface's reason (a partial/failed read is never a silent gap); transport errors propagate.
 * @param {object} client  a connected apps/desktop/ipc/client IpcClient (has controlEvent)
 * @returns {object} the governor status dict {ref: {provider, allowance, active, in_use}}
 */
async function fetchSubscriptionStatus(client) {
  const payload = await client.controlEvent({ op: "subscription_status" });
  if (!payload || payload.ok !== true) {
    throw new StatusBarSourceError(
      `subscription_status failed: ${payload && payload.error ? payload.error : "no ok payload"}`,
    );
  }
  return payload.result;
}

/**
 * Build the status-bar model from the live governor count. DISPLAY contract: NEVER throws — the
 * status bar is always visible, so any fault degrades to a fail-closed unknown model (no fabricated
 * count) with the reason attached, rather than propagating into the renderer.
 * @returns {{readable, cap, providers, rows, summary, error?:string}}
 */
async function fetchStatusBarModel(client, opts = {}) {
  try {
    const status = await fetchSubscriptionStatus(client);
    const model = buildStatusBarModel({ status, ...opts });
    return { ...model, summary: summarizeStatusBar(model) };
  } catch (e) {
    // fail closed: unknown rows, no numbers invented; the error is surfaced for observability.
    const model = buildStatusBarModel({ status: null, ...opts });
    return { ...model, summary: summarizeStatusBar(model), error: `${e.name || "Error"}: ${e.message}` };
  }
}

module.exports = { StatusBarSourceError, fetchSubscriptionStatus, fetchStatusBarModel };
