"use strict";
/**
 * Conductor-first LAYOUT reconstruction (product code, terminal/). Phase 15E `.recovery`.
 *
 * Directive §9 track 14A ("UI recovery after process restart") + OP-7 §12.4 (conductor-first
 * startup) + OP-8 §13 (the conductor is a live interactive pane): after a full shell-PROCESS
 * restart the workspace must come back with the pinned CONDUCTOR as pane 1 and the worker panes
 * REATTACHING to what existed — never as naked live sessions (invariant 2). Its sibling
 * `reconstruct.js` folds the append-only session lifecycle log into per-session dispositions;
 * THIS module folds the persisted PANE-LAYOUT snapshot together with that session view (and the
 * current supervision admission state) into the ordered conductor-first layout the shell rebuilds.
 * Pure/deterministic: no clock, no I/O, no Node — the rendered window is an operator-run surface
 * (directive §6); this logic is headless-tested.
 *
 * Two fail-closed rules carry the invariants:
 *  1. Conductor-first is STRUCTURAL, not data-driven (OP-7 §12.4): the reconstructed layout ALWAYS
 *     has the pinned CONDUCTOR as pane 1, rebuilt from the operator SELECTION even when the
 *     snapshot's conductor entry is missing/blank. The badge shows the selection label, honestly
 *     `awaiting_live_conductor` — never a fabricated live checkpoint (invariant 3), never a naked
 *     re-spawned session (the live interactive launch is governed + operator-run, §6/§13).
 *  2. No pane reattaches to a LIVE session on boot (invariant 2). A pane whose session was still
 *     alive at the cut comes back `needsRelaunch` / `reattach:false`; and while the control-plane
 *     channel is not re-verified (`admissionOpen:false`) EVERY pane is `admitted:false` /
 *     awaiting-supervision — no naked session during the gap, re-admit only on a verified channel.
 */

const LAYOUT_FORMAT_VERSION = 1;
const CONDUCTOR_LABEL = "CONDUCTOR";

function _nonBlank(s) {
  return typeof s === "string" && s.trim() ? s.trim() : null;
}

/**
 * Whitelisted, deterministic capture of the per-pane governed CHROME the operator sees on a worker
 * pane (Phase 16D `.recovery`, closes U68): the model badge (label / slug / verified), provider +
 * locality, role + mode, the HONEST node_state + governed flag, subscription allowance, residency.
 * ONLY known fields are captured — never a blind copy of the caller's object (determinism + no
 * fabricated/leaked field survives a round-trip); a missing chrome yields null so a worker with no
 * recorded picker selection snapshots honestly as chrome:null / model null (invariant 3, never a
 * fabricated model). Re-run on the disk-loaded value at reconstruct time too, so a corrupt snapshot
 * degrades to null rather than propagating garbage into the rebuilt badge.
 */
function _chromeSnapshot(c) {
  if (!c || typeof c !== "object") return null;
  const sub = c.subscription;
  return {
    provider: _nonBlank(c.provider),
    adapter: _nonBlank(c.adapter),
    locality: _nonBlank(c.locality),
    model_label: _nonBlank(c.model_label),
    model_slug: _nonBlank(c.model_slug),
    model_verified: c.model_verified === true,
    role: _nonBlank(c.role),
    mode: c.mode === "attended" ? "attended" : "autonomous", // fail-closed default: autonomous
    node_state: _nonBlank(c.node_state),
    // Carried verbatim from the snapshot, whatever it says. Since 17B `.spawn` a worker pane's
    // chrome CAN legitimately read governed:true — a picker click now launches a real governed
    // session — and main revises it to governed:false when that session ends, so what is captured
    // here is the last recorded truth about the pane, not a standing "nothing was ever launched".
    // What is captured is NOT what is restored: see `_sanitizeRestoredChrome`, which is applied on
    // the reconstruct side because a captured `running` was true when written and is false by
    // construction after a restart.
    governed: c.governed === true,
    subscription: sub && typeof sub === "object"
      ? {
        allowance: typeof sub.allowance === "number" ? sub.allowance : null,
        in_use: typeof sub.in_use === "number" ? sub.in_use : null,
      }
      : null,
    residency: _nonBlank(c.residency),
  };
}

/**
 * `node_state` values that assert a process is ALIVE RIGHT NOW. A reconstructed pane has no live
 * session BY CONSTRUCTION — every worker below comes back `reattach:false` / `admitted:false` and
 * the shell re-admits nothing on boot (invariant 2) — so a restored chrome may never carry one.
 */
const LIVE_NODE_STATES = new Set(["running", "launching", "session_terminating", "live", "ready"]);
/** What a pane whose live session did not outlive the shell reads instead. */
const INTERRUPTED_NODE_STATE = "session_interrupted";

/**
 * Make a RESTORED chrome honest about the present (invariants 3/27).
 *
 * `main.markWorkerPaneChromeEnded` corrects a worker pane's chrome when its session ends, so an
 * orderly shutdown persists `session_exited`/`session_killed` and this function has nothing to do.
 * But that revision rides an exit/kill EVENT: a SIGKILL, a main-process crash or a power cut —
 * precisely the deaths a recovery module exists for — leave `{node_state:"running", governed:true}`
 * on disk, and the renderer renders `node_state === "running"` as the badge text **live**. On the
 * next boot `paneSeq` restarts at 0, so the operator's first new worker pane takes the very pane id
 * most likely to be in the stale snapshot, and a brand-new empty pane came up badged `· live` for a
 * process that died with the last shell (gate-validator MAJOR-1 / spec-audit MAJOR-1, 2026-07-26).
 *
 * A stale live state is therefore REWRITTEN, not carried: `node_state` becomes
 * `session_interrupted` and `governed` false, because there is no governed node here right now.
 * The fact is not erased — `interrupted_from` records what the pane was doing when the shell died,
 * which is the true statement the snapshot supports ("this pane WAS running") in place of the false
 * one it used to make ("this pane IS running"). The model badge itself is untouched: the operator
 * picked that model and it is still what the pane last ran.
 *
 * Derived at the FOLD, never carried from disk: `_chromeSnapshot`'s whitelist drops any
 * `interrupted_from` a corrupt/forged snapshot supplies before this runs.
 */
function _sanitizeRestoredChrome(c) {
  if (!c) return null;
  const stale = c.node_state && LIVE_NODE_STATES.has(String(c.node_state).toLowerCase());
  if (!stale && c.governed !== true) return { ...c, interrupted_from: null };
  return {
    ...c,
    node_state: stale ? INTERRUPTED_NODE_STATE : c.node_state,
    // false on BOTH branches: `governed:true` asserts a governed node exists in this pane, and after
    // a restart none does — whatever the last shell wrote about the pane it no longer holds.
    governed: false,
    interrupted_from: stale ? String(c.node_state) : null,
  };
}

/**
 * Capture the CURRENT pane layout as a persistable snapshot (called before the shell dies, on
 * every layout-affecting change). Reads only the deterministic PaneModel state plus an optional
 * per-pane chrome lookup (`meta(id) -> {role, mode, model, nodeId}`) for the facts the model does
 * not itself hold (which model a worker pane runs, attended vs autonomous). Pure — no I/O.
 *
 * @param {object}   args
 * @param {object}   args.panes            PaneModel (uses its public `.order` + `.get(id)`)
 * @param {string?}  args.conductorPaneId  the pinned pane-1 conductor node id (or null)
 * @param {function} [args.meta]           id -> {role, mode, model, nodeId, chrome?}; missing ⇒ defaults
 *                                         (chrome = the governed per-pane badge, captured for U68)
 * @returns {{version:number, conductor:object|null, panes:Array}}
 */
function buildLayoutSnapshot({ panes, conductorPaneId = null, meta = () => ({}) }) {
  const order = panes && Array.isArray(panes.order) ? panes.order : [];
  let conductor = null;
  const workers = [];
  let ordinal = 1; // pane 1 is reserved for the conductor; workers start at 2
  for (const id of order) {
    let p;
    try { p = panes.get(id); } catch { continue; } // a pane vanished mid-read — skip, never fabricate
    const m = (meta(id) || {});
    if (id === conductorPaneId) {
      conductor = {
        paneId: id,
        ordinal: 1,
        pinned: p.pinned === true,
        model: _nonBlank(m.model),        // selection label if known; null ⇒ rebuilt from selection at fold
        sessionId: p.sessionId || null,   // normally null: the conductor is a placeholder until the live launch
      };
      continue;
    }
    ordinal += 1;
    workers.push({
      paneId: id,
      ordinal,
      role: _nonBlank(m.role) || "worker",
      mode: m.mode === "attended" ? "attended" : "autonomous", // fail-closed default: autonomous
      model: _nonBlank(m.model),
      // Phase 16D `.recovery` (U68): the full governed pane CHROME the operator sees, so a restored
      // worker pane repaints its exact model badge instead of coming back blank. null ⇒ a pane with
      // no recorded picker selection (honest, never fabricated).
      chrome: _chromeSnapshot(m.chrome),
      pinned: p.pinned === true,
      sessionId: p.sessionId || null,
      nodeId: _nonBlank(m.nodeId),
      windowState: _nonBlank(p.windowState) || "normal",
    });
  }
  return { version: LAYOUT_FORMAT_VERSION, conductor, panes: workers };
}

/**
 * The pinned pane-1 CONDUCTOR entry — ALWAYS present (conductor-first is structural, OP-7 §12.4).
 * Rebuilt from the operator selection; `awaiting_live_conductor` and never auto-attached (the live
 * interactive session is a governed, operator-run launch, §13). `admitted` tracks whether the
 * channel is currently verified — false during the recovery gap (no naked session, invariant 2).
 */
function _conductorEntry(snapshotConductor, selection, admissionOpen) {
  const sc = snapshotConductor || {};
  const sel = selection || {};
  return {
    paneId: sc.paneId || null,          // the shell assigns pane-1 fresh when the snapshot has none
    ordinal: 1,
    role: "conductor",
    label: CONDUCTOR_LABEL,
    pinned: true,                       // conductor-first ⇒ pinned P0, always visible
    mode: "attended",                   // the operator talks to it (OP-8 §13.2)
    model: _nonBlank(sel.model) || _nonBlank(sc.model) || "(unknown selection)",
    verified: sel.verified === true,    // only true when a live reply reported the executing checkpoint
    isFallback: sel.isFallback === true,
    nodeState: "awaiting_live_conductor", // honest: reconstructed as a placeholder, not a live session
    reattach: false,                    // re-established via the governed live launch, never auto-attached
    admitted: admissionOpen === true,   // re-admittable only on a verified channel
  };
}

/**
 * Fold a persisted layout snapshot + the reconstructed session view + the current admission state
 * into the conductor-first layout the shell rebuilds after a full process restart. Fail-closed on
 * every axis (see module header). Pure/deterministic.
 *
 * @param {object}   args
 * @param {object?}  args.snapshot        buildLayoutSnapshot(...) output (null/corrupt ⇒ conductor-only)
 * @param {Array?}   args.sessions        reconstructSessions(...) output (per-session dispositions)
 * @param {boolean}  args.admissionOpen   is the control-plane channel currently re-verified?
 * @param {object?}  args.selection       operator conductor selection {model, verified?, isFallback?}
 * @returns {object} the reconstructed conductor-first layout
 */
function reconstructLayout({ snapshot = null, sessions = [], admissionOpen = false, selection = null } = {}) {
  const open = admissionOpen === true;
  const snap = snapshot && typeof snapshot === "object" ? snapshot : null;
  // index the reconstructed session view by id (== paneId sessionId) for O(1) disposition lookup
  const byId = new Map();
  for (const s of Array.isArray(sessions) ? sessions : []) {
    if (s && s.id != null) byId.set(s.id, s);
  }

  const conductor = _conductorEntry(snap ? snap.conductor : null, selection, open);

  const workers = [];
  const snapPanes = snap && Array.isArray(snap.panes) ? snap.panes : [];
  let ordinal = 1;
  for (const w of snapPanes) {
    if (!w || !w.paneId) continue; // never fabricate a pane
    ordinal += 1;
    const sid = w.sessionId || null;
    const sess = sid != null ? byId.get(sid) : undefined;

    // Disposition + relaunch decision, fail-closed:
    //  - a session found in the log carries its own disposition (interrupted ⇒ needsRelaunch).
    //  - a pane that HAD a session but whose record is absent from the log has an unknown fate ⇒
    //    surface it for supervised relaunch (never assume a clean exit).
    //  - a pane with no session (a placeholder) needs no relaunch.
    let disposition;
    let needsRelaunch;
    let lastState;
    if (sess) {
      disposition = sess.disposition || "unknown";
      needsRelaunch = sess.needsRelaunch === true;
      lastState = sess.lastState || null;
    } else if (sid != null) {
      disposition = "absent";      // pane referenced a session with no lifecycle record
      needsRelaunch = true;        // fail-closed: unknown fate ⇒ relaunch under supervision
      lastState = null;
    } else {
      disposition = "none";        // placeholder pane, never had a session
      needsRelaunch = false;
      lastState = null;
    }

    const paneState = needsRelaunch ? "awaiting_supervision" : (disposition === "none" ? "empty" : "ended");

    workers.push({
      paneId: w.paneId,
      ordinal,
      role: _nonBlank(w.role) || "worker",
      mode: w.mode === "attended" ? "attended" : "autonomous",
      model: _nonBlank(w.model),
      // Phase 16D `.recovery` (U68): carry the persisted governed chrome through the fold, re-sanitized
      // so a corrupt snapshot degrades to null (a blank badge, never fabricated). This is a RECORDED
      // selection restored — the chrome records what that pane last RAN (17B `.spawn`: node_state
      // may read `session_exited`/`session_killed`, or `running` if the shell was KILLED before it
      // could revise it). The restored chrome claims no live node, and since 2026-07-26 that is
      // ENFORCED rather than asserted: `_sanitizeRestoredChrome` rewrites a stale live state to
      // `session_interrupted` / `governed:false` (keeping what it was in `interrupted_from`), so the
      // badge cannot read `live` for a process that died with the last shell. The worker below is
      // also reattach:false / not admitted (invariant 2, no naked re-spawn on boot).
      chrome: _sanitizeRestoredChrome(_chromeSnapshot(w.chrome)),
      pinned: w.pinned === true,
      sessionId: sid,
      disposition,
      lastState,
      needsRelaunch,
      // invariant 2: a worker is NEVER auto-attached to a live session on boot, and can only be
      // re-admitted through supervised relaunch on a re-verified channel — so it is never `admitted`
      // by reconstruction alone (the operator relaunches it; admission is re-checked then).
      reattach: false,
      admitted: false,
      paneState,
    });
  }

  const interrupted = workers.filter((w) => w.needsRelaunch).map((w) => w.paneId);
  return {
    version: LAYOUT_FORMAT_VERSION,
    admissionOpen: open,
    conductor,
    panes: workers,
    interrupted,
    summary: {
      total: workers.length + 1, // conductor + workers
      workers: workers.length,
      interrupted: interrupted.length,
      admissionOpen: open,
    },
  };
}

/**
 * W-64: the mint-counter seeding contract for a restarted shell.
 *
 * The persisted layout snapshot reuses the `pane-N` id namespace while the shell's
 * mint counter restarted at 0 on every boot, so a fresh bare shell could re-mint an
 * id a dead governed pane still holds in the snapshot - and inherit that pane's
 * model badge. The seed is the floor that makes that collision impossible without
 * redesigning pane identity: new mints start ABOVE every `pane-N` id the snapshot
 * holds (conductor entry included). Only ids of the exact shape `pane-<digits>`
 * count; a missing/corrupt snapshot contributes nothing and the caller's current
 * value passes through unchanged. Pure/deterministic.
 */
function resumePaneSeq({ snapshot = null, paneSeq = 0 } = {}) {
  const snap = snapshot && typeof snapshot === "object" ? snapshot : null;
  let max = typeof paneSeq === "number" && Number.isFinite(paneSeq) ? paneSeq : 0;
  const ids = [];
  if (snap && snap.conductor && snap.conductor.paneId != null) ids.push(snap.conductor.paneId);
  if (snap && Array.isArray(snap.panes)) {
    for (const w of snap.panes) if (w && w.paneId != null) ids.push(w.paneId);
  }
  for (const id of ids) {
    const m = /^pane-(\d+)$/.exec(String(id));
    if (!m) continue;
    const n = parseInt(m[1], 10);
    if (Number.isFinite(n) && n > max) max = n;
  }
  return max;
}

module.exports = {
  LAYOUT_FORMAT_VERSION,
  CONDUCTOR_LABEL,
  LIVE_NODE_STATES,
  INTERRUPTED_NODE_STATE,
  buildLayoutSnapshot,
  reconstructLayout,
  resumePaneSeq,
};
