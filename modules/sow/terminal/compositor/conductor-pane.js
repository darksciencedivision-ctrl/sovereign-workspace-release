"use strict";
/**
 * Conductor-first pane chrome (product code, terminal/). Phase 15E `.conductor-pane`
 * (directive §13 / OP-8; OP-7 §12.4 conductor-first startup).
 *
 * Pure/deterministic render model for pane 1's CONDUCTOR badge and the Resume→Select succession
 * control — no time, no I/O, no Node. The governed facts (which model, verified?, subscription
 * n/2, the interactive launch, the live gates) are produced by the Python
 * `node_runtime/supervisor/conductor_pane_spawn.spawn_conductor_pane`; this module only shapes what
 * the sandboxed renderer draws from whatever selection/chrome record it is given (the live path that
 * delivers those governed facts over IPC is wired in a later 15E sub-step). It NEVER fabricates a model
 * id: a missing/blank selection renders as an explicit "unknown selection", and an unverified
 * executing checkpoint renders as unverified (invariant 3 — the badge shows the operator SELECTION
 * label, not a guessed checkpoint).
 *
 * The actual pinned pane-1 placement uses PaneModel.pin (pinned ⇒ tiling P0, never auto-collapsed),
 * so the conductor pane is always visible. The rendered window itself is an operator-run surface
 * (directive §6) like the rest of the shell; this pure logic is headless-tested.
 */
const CONDUCTOR_LABEL = "CONDUCTOR";
const SUCCESSION_LABEL = "Resume→Select";

function _nonBlank(s) {
  return typeof s === "string" && s.trim() ? s.trim() : null;
}

/**
 * The CONDUCTOR model badge from a conductor selection record
 * (`ConductorBinding.as_record()` shape: {selection:{model,...}, executing:{model,verified,is_fallback,...}}).
 * Fail-closed: a missing selection model renders "(unknown selection)"; `verified` is only ever
 * true when the record says a live reply reported the executing checkpoint.
 */
function conductorBadge(selectionRecord) {
  const rec = selectionRecord || {};
  const sel = rec.selection || {};
  const exec = rec.executing || {};
  return {
    label: CONDUCTOR_LABEL,
    model: _nonBlank(sel.model) || "(unknown selection)",
    verified: exec.verified === true, // false until a live reply reports the executing checkpoint
    isFallback: exec.is_fallback === true,
    executing: _nonBlank(exec.model), // the reported checkpoint id, or null when nothing ran
    mode: "attended", // the operator talks to it (OP-8 §13.2)
    pinned: true,
    paneOrdinal: 1,
  };
}

/**
 * The Resume→Select control drawn from a succession affordance
 * (`conductor_succession_affordance(...)`). Fail-closed to unavailable when the affordance is
 * missing or not marked available — the control is never shown active on a shape it cannot trust.
 */
function conductorSuccessionControl(affordance) {
  if (!affordance || affordance.available !== true) {
    return { available: false, label: SUCCESSION_LABEL, reason: "succession affordance unavailable" };
  }
  return {
    available: true,
    label: SUCCESSION_LABEL,
    actions: Array.isArray(affordance.actions) ? affordance.actions.slice() : [],
    restoreTarget: _nonBlank(affordance.restore_target),
  };
}

/**
 * The pane-1 conductor-first spec the shell renders from a conductor-pane chrome
 * (`ConductorPaneChrome.as_dict()`). Fail-closed: a chrome that is not the conductor role is
 * refused — a worker pane must never be branded CONDUCTOR (invariant 3).
 */
function conductorPaneSpec(chrome) {
  if (!chrome || chrome.role !== "conductor") {
    throw new Error("conductorPaneSpec requires a conductor-role chrome (never brand a worker CONDUCTOR)");
  }
  const badge = conductorBadge({
    selection: { model: chrome.model_label },
    executing: { model: null, verified: chrome.model_verified === true, is_fallback: chrome.is_fallback === true },
  });
  return {
    ordinal: chrome.pane_ordinal || 1,
    pinned: chrome.pinned === true,
    label: CONDUCTOR_LABEL,
    role: "conductor",
    mode: chrome.mode || "attended",
    interactive: chrome.interactive === true,
    governed: chrome.governed === true,
    nodeState: _nonBlank(chrome.node_state) || "unknown",
    subscription: chrome.subscription || null,
    badge,
    succession: conductorSuccessionControl(chrome.succession),
  };
}

module.exports = {
  CONDUCTOR_LABEL,
  SUCCESSION_LABEL,
  conductorBadge,
  conductorSuccessionControl,
  conductorPaneSpec,
};
