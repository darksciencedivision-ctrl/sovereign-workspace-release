"use strict";
/**
 * WORKER-PANE WIRING RULES — the governance that lived in `main.js` and therefore could not be seen.
 *
 * Phase 17B `.spawn-revalidate`. The `.spawn` reviews found the same defect class twice, one round
 * apart: a rule was correct in `main.js`, and NOTHING in the repo could tell whether it stayed
 * correct. `main.js` is the Electron entry point — it cannot be required headlessly (it calls
 * `app.whenReady()` at load), so a rule written there has no unit test by construction, and the
 * in-Electron receipt only sees what it happens to assert. Three rules were in exactly that state
 * (spec-audit MAJOR-2 / validator MINOR-2, 2026-07-26):
 *
 *   1. the post-spawn ROLLBACK — the fix for "a spawn that throws means nothing was born";
 *   2. the ENDED-chrome revision — the fix for "a dead pane kept badging itself live";
 *   3. the CONDUCTOR-PANE guard — the fix for "a worker could be launched into pane 1".
 *
 * Reverting any of them left every suite green. They are pure/injectable here so the headless suite
 * drives each one, exactly as `worker-spawn.js` exists so the launcher's rules are drivable; `main.js`
 * keeps the wiring (the real SessionManager, the real PaneModel, the real window) and no rules.
 */

/** The pane chrome fields that describe a LIVE session rather than the operator's selection. */
const LIVE_CHROME_STATE = "running";
const TERMINATING_CHROME_STATE = "session_terminating";

/**
 * A governed worker pane's session ended (its own exit, an operator close, or the fail-closed
 * `killAll` on supervision loss): what its chrome must say now. PURE — returns the corrected chrome,
 * or `null` when there is nothing to correct (no chrome, or a chrome that never claimed a live
 * session, so an exit event for an unrelated pane can never invent one).
 *
 * The model badge is KEPT: the operator picked that model and it is still what this pane last ran.
 * `node_state` / `governed` / `pid` describe a node that no longer exists, so they are corrected —
 * and because this corrected chrome is what the layout snapshot carries, the correction is also what
 * the NEXT BOOT replays. Before this existed, `paneMeta()` still reported `node_state:"running",
 * governed:true` after an ordinary exit and after the fail-closed kill on supervision loss — i.e.
 * exactly when supervision is GONE — and every later snapshot baked that in (spec-audit MAJOR-1,
 * invariants 3/27).
 *
 * @param {object|null} chrome  the pane's current chrome
 * @param {object} event        the session lifecycle event `{kind:"exit"|"kill", exitCode?}`
 * @returns {object|null} the corrected chrome, or null when nothing needs correcting
 */
function endedWorkerChrome(chrome, event = {}) {
  if (!chrome || typeof chrome !== "object") return null;
  if (![LIVE_CHROME_STATE, TERMINATING_CHROME_STATE].includes(chrome.node_state)) return null;
  // Pane ids are reusable views. A delayed callback from an older process must never darken the
  // replacement's chrome, so the view carries the same exact process identity as the launch record.
  if (!Number.isInteger(chrome.pid) || !Number.isInteger(chrome.session_generation)
      || event.pid !== chrome.pid || event.generation !== chrome.session_generation) return null;
  const terminating = event.kind === "kill" && event.processExited === false;
  const exited = event.kind === "exit" && event.processExited === true;
  if (!terminating && !exited) return null;
  return {
    ...chrome,
    node_state: terminating ? TERMINATING_CHROME_STATE : "session_exited",
    governed: terminating,
    pid: terminating ? chrome.pid : null,
    launch_reason: terminating ? "session termination requested" : `session exited (${event.exitCode})`,
  };
}

/**
 * The shell's SUPERVISED spawn, as the launcher's `spawnSession` dependency — with the rollback that
 * makes the launcher's contract true.
 *
 * `worker-spawn.js` distinguishes a pre-birth throw from a post-birth rollback. The wiring does five
 * more things after `manager.spawn` succeeds (create the pane, attach it, persist, push, relayout).
 * Any of them throwing without killing the session would leave a live `claude` behind. Therefore a
 * post-birth failure requests termination and rethrows with exact process identity; the launcher
 * retains the durable I-X3 terminal until that PID/generation's `onExit` confirms death.
 *
 * The pid read is INSIDE the same guard: `registry.get` throws on an unknown session, and a throw
 * from here must carry the registered process identity rather than masquerade as a pre-birth failure
 * (spec-audit MINOR-4). Effectively unreachable today; it is guarded because exact identity is what
 * makes terminal accounting sound.
 *
 * Rollback is best-effort BY DESIGN: if `manager.kill` itself throws, the exact registered identity
 * is still attached to the error and its terminal remains held. What it may never do is swallow the
 * fault, report a launch, or tell the caller to release before confirmed exit.
 *
 * @param {object} deps  `{manager, panes, persistLayoutSnapshot, pushState, emitLayoutNow, log}`
 * @returns {function} `({paneId, nodeId, spec}) -> {pid,generation}`
 */
function createGovernedPaneSpawn(deps = {}) {
  const {
    manager,
    panes,
    persistLayoutSnapshot = () => {},
    pushState = () => {},
    emitLayoutNow = () => {},
    log = () => {},
  } = deps;
  if (!manager || !panes) {
    throw new Error("createGovernedPaneSpawn requires the real manager + pane model — the supervised "
      + "spawn is the only way a governed session is born (invariant 2)");
  }
  return function spawnGovernedPane({ paneId, nodeId, spec }) {
    let identity = null;
    try {
      // Spawn FIRST: if supervision denies it or ConPTY fails, no pane was created, so a refused
      // launch leaves no empty pane on the operator's screen.
      const session = manager.spawn({ id: paneId, nodeId, spec });
      if (session && Number.isInteger(session.pid) && Number.isInteger(session.generation)) {
        identity = { pid: session.pid, generation: session.generation };
      }
      if (!panes.panes.has(paneId)) panes.createPane({ id: paneId, title: (spec && spec.title) || "worker" });
      panes.attachSession(paneId, paneId);
      persistLayoutSnapshot();
      pushState();
      emitLayoutNow(); // create the pane's xterm view immediately (16A) — scrollback covers the gap
      const rec = manager.registry.get(paneId);
      if (!rec || !Number.isInteger(rec.pid) || !Number.isInteger(rec.generation)) {
        throw new Error("the supervised session registry did not return an exact pid + generation");
      }
      return { pid: rec.pid, generation: rec.generation };
    } catch (e) {
      if (!e.sessionIdentity && identity) {
        try { manager.kill(paneId); } catch { /* the session may already be terminal */ }
        e.sessionIdentity = identity;
        const current = typeof manager.processIdentity === "function"
          ? manager.processIdentity(paneId) : identity;
        e.processExitPending = Boolean(current
          && current.pid === identity.pid && current.generation === identity.generation);
      }
      log(`worker pane ${paneId}: post-spawn wiring failed (${e.message}) — session killed, launch rolled back`);
      throw e;
    }
  };
}

/**
 * The fail-closed selection guard — mirrors the refusals in
 * `pane_node_spawn.spawn_node_from_selection` so a selection the Python dispatcher would refuse is
 * never presented as spawnable in the UI. A UX guard, NOT the authority (Python re-enforces every
 * gate). Returns a refusal reason string, or `null` when the selection passes the front-line checks.
 *
 * PURE, and it takes `conductorPaneId` as an argument rather than reading a module global, for the
 * reason the last line exists: the conductor-pane rule was moved OUT of a CSS class and into
 * governance (validator MINOR-4) and then had no test at all, because it lived in `main.js`.
 */
function refuseSelection(sel, { conductorPaneId = null, hostOptions = null } = {}) {
  const supplied = sel && sel.option;
  if (!supplied || typeof supplied !== "object") return "selection carries no picker option (fail closed)";
  // W-37: judge the option the HOST offers, not the one the caller handed us. Every check below
  // used to read `sel.option` directly, so a caller supplying `available: true` and the roles it
  // wanted passed the whole guard — the guard was asking the claim about itself.
  //
  // The donor is `main.js`'s conductor pre-launch path: it re-finds the supplied option in the last
  // picker model by (adapter, model_slug, label) and judges the RE-FOUND one. `hostVerifiedFlag`
  // does it again and states the rule outright — an option this host does not currently offer, "a
  // fabricated one, or a stale one", is not verified whatever the caller claimed. The worker picker
  // never got that treatment.
  //
  // NOT OPTIONAL. A caller that supplies no host model is refused rather than waved through:
  // corroboration that can be skipped is corroboration nobody performs.
  if (!Array.isArray(hostOptions)) {
    return "no host picker model was supplied to corroborate this selection (fail closed) — the "
      + "shell judges what the host offers, never what the caller claims";
  }
  const opt = hostOptions.find((h) => h && h.adapter === supplied.adapter
    && h.model_slug === supplied.model_slug && h.label === supplied.label);
  if (!opt) {
    return `option ${supplied.provider}/${supplied.label} is not offered by this host (fail closed) `
      + "— a fabricated or stale option is never spawnable, whatever the selection claims";
  }
  if (!opt.available) return `option ${opt.provider}/${opt.label} is unavailable (${opt.unavailable_reason || "no reason recorded"}) — cannot spawn a greyed option`;
  if (sel.mode !== "attended" && sel.mode !== "autonomous") return `unknown pane mode ${JSON.stringify(sel.mode)} — expected attended|autonomous`;
  const offered = Array.isArray(opt.roles) ? opt.roles : [];
  if (!offered.includes(sel.role)) return `role ${JSON.stringify(sel.role)} not offered by ${opt.provider}/${opt.label} (offered: ${offered.join("|")}) — never inferred (I-SC1)`;
  if (sel.role === "conductor") return "the conductor role is spawned by the dedicated conductor-first path (16C), not the worker picker — deferred, not unavailable";
  // …and not into the CONDUCTOR PANE either. The role guard above stops a worker pane being given
  // the conductor role; nothing stopped a WORKER role being launched into pane 1, whose chrome,
  // recovery pinning and relaunch control all belong to the conductor path — the only thing in the
  // way was a CSS rule hiding the picker on that pane, i.e. governance in the least-trusted layer
  // (validator MINOR-4). Pane 1 is the conductor's; it is spawned and replaced by its own path.
  if (sel.targetPaneId && conductorPaneId && sel.targetPaneId === conductorPaneId) {
    return `pane ${conductorPaneId} is the CONDUCTOR pane — a worker model is never launched into it `
      + "(use Resume→Select to change the conductor's backend)";
  }
  return null;
}

module.exports = {
  endedWorkerChrome, createGovernedPaneSpawn, refuseSelection,
  LIVE_CHROME_STATE, TERMINATING_CHROME_STATE,
};
