"use strict";
/**
 * Preload: the ONLY bridge between the sandboxed renderer and the main process.
 *
 * The renderer has no Node integration (TB-2 / invariant 29): it cannot spawn a PTY, open a
 * socket, or touch the filesystem. It can only send the intents enumerated here, each of which
 * lands on a governed main-process handler. Anything a model prints into a terminal is untrusted
 * output and is never routed back through this bridge as a command.
 */
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("sovereign", {
  // pane / session intents (main enforces supervision + validity)
  newPane: (spec) => ipcRenderer.invoke("pane:new", spec),
  createEmptyPane: (spec) => ipcRenderer.invoke("pane:create-empty", spec),
  selectExecution: (payload) => ipcRenderer.invoke("pane:select-execution", payload),
  // G25: persistent operator typing surface - text goes through the SAME guarded
  // delivery path voice chat uses (deliverConductorChat); never straight to a PTY.
  sendOperatorText: (text, sweep = false) => ipcRenderer.invoke(
    "conductor:operator-text", sweep ? { text, __sweep: true } : { text }),
  onConductorTranscript: (cb) => ipcRenderer.on("shell:conductor-transcript", (_e, t) => cb(t)),
  input: (id, data) => ipcRenderer.invoke("pane:input", id, data),
  // Phase 16A: byte-exact scrollback for a pane's session, replayed when the term view (re)attaches.
  // Returns {text, seq} — the snapshot plus the seq of the last chunk it includes. READ-ONLY.
  scrollback: (id) => ipcRenderer.invoke("pane:scrollback", id),
  resize: (id, cols, rows) => ipcRenderer.invoke("pane:resize", id, cols, rows),
  close: (id) => ipcRenderer.invoke("pane:close", id),
  focus: (id) => ipcRenderer.invoke("pane:focus", id),
  maximize: (id) => ipcRenderer.invoke("pane:maximize", id),
  restore: (id) => ipcRenderer.invoke("pane:restore", id),
  minimize: (id) => ipcRenderer.invoke("pane:minimize", id),
  pin: (id, on) => ipcRenderer.invoke("pane:pin", id, on),
  setActivity: (id, activity) => ipcRenderer.invoke("pane:activity", id, activity),
  snapshot: () => ipcRenderer.invoke("shell:snapshot"),

  // per-pane model picker (Phase 16B; OP-7 §12.2 / OP-10 §15) — READ-ONLY pull of the live host
  // enumeration {ok, picker:{providers,options,authorization,counts}} or {ok:false, error, picker}.
  // Fail-closed: a fault yields the empty picker, never a fabricated option. No new renderer authority.
  picker: () => ipcRenderer.invoke("picker:fetch"),
  // select one option → the governed pane_node_spawn path. RECORDS the governed selection and
  // returns {recorded, chrome} (or {recorded:false, error} for a fail-closed refusal). It grants the
  // renderer NO authority (invariant 1) and starts no session (invariant 2): the live governed spawn
  // is operator-run/16F (U25 gates the IPC write) — exactly as decideApproval/captureVoice record.
  spawnFromSelection: (sel) => ipcRenderer.invoke("pane:spawnFromSelection", sel),

  // routing/artifact inspector (§10.3) — READ-ONLY pull of governed MCP state; returns
  // {ok, model, summary, routingReadable} or {ok:false, error}. No new renderer authority.
  inspector: () => ipcRenderer.invoke("inspector:fetch"),

  // subscription-concurrency status bar (§11/15A) — READ-ONLY pull of the governor n/2 count;
  // returns a status-bar model {readable, cap, rows, summary, error?}. Fail-closed (unknown rows,
  // never a fabricated count) on any fault. No new renderer authority.
  statusBar: () => ipcRenderer.invoke("statusbar:fetch"),

  // conductor-first pane (§13/§12.4) — READ the CONDUCTOR badge + Resume→Select control state; and
  // REQUEST a succession (Resume→Select). The succeed intent only RECORDS the operator's request (an
  // acknowledged log entry) — it grants the renderer no authority (invariant 1); wiring it through to
  // the governed Python succession path (15D SuccessionManager) is deferred to a later 15E sub-step.
  conductorState: () => ipcRenderer.invoke("conductor:state"),
  // Phase 17A `.pty`: ask pane 1 to run its REAL interactive conductor session (the explicit
  // operator control alongside the on-launch spawn). The renderer gains NO authority (invariant 1):
  // the ticket is issued by the governed Python path and the spawn goes through the supervised
  // session manager, which refuses without an admitted node. Returns {launched, reason?}.
  launchConductor: () => ipcRenderer.invoke("conductor:launch"),
  selectConductor: (sel) => ipcRenderer.invoke("conductor:select", sel),
  succeedConductor: () => ipcRenderer.invoke("conductor:succeed"),

  // operator command surface (§12.5 item 5) — READ the approval-queue drawer model {ok, badgeCount,
  // kindCounts, rows, summary}; and RECORD an operator approve/reject request. The decide intent only
  // RECORDS the request (a logged entry) — it grants the renderer no authority (invariant 1); the
  // governed resolve lives in the Python ApprovalQueue / ObjectiveIntake / CommandBroker (owed IPC
  // routing, U66). Fail-closed: an unavailable feed returns an empty drawer, never a fabricated item.
  approvals: () => ipcRenderer.invoke("approvals:fetch"),
  decideApproval: (itemId, decision, reason) => ipcRenderer.invoke("approvals:decide", itemId, decision, reason),

  // conductor voice-IN (§13.5; Phase 16E `.wire`, closes the WRITE half of U67) — READ the push-to-talk
  // mic affordance/state {control, badge, summary, engine, speechOut:false} with the VISIBLE mock/real
  // engine indicator; and CAPTURE — route one utterance through the REAL Python ConductorVoiceBridge and
  // return {sourced, engine, outcome, delivered_to_conductor, queued, needs_clarification, selfAuthorized:
  // false, ...}. The renderer grants itself no authority (invariant 1/25): a CHAT is delivered into the
  // conductor input (same command path as typing), a protected/destructive action is QUEUED for approval
  // (never delivered), a low-confidence transcript clarifies — all decided Python-side. STT-only: there
  // is deliberately NO speech-out intent (I-V2/D-VOICE-02: no TTS).
  voiceState: () => ipcRenderer.invoke("voice:state"),
  captureVoice: (audioRef) => ipcRenderer.invoke("voice:capture", audioRef),
  // Phase 17C `.probe` (U74): ask for the STT engine state. The probe is ASYNCHRONOUS — `voiceState()`
  // answers instantly with `probing…` while this is in flight, so the always-visible chrome never
  // stalls on WSL and never renders an unanswered probe as a "mock engine" verdict. `{force:true}`
  // re-takes the probe (the operator's retry after finishing the NeMo install).
  probeVoice: (opts) => ipcRenderer.invoke("voice:probe", opts || {}),

  // main -> renderer streams
  // pane:data carries a per-session monotonic `seq` (Phase 16A) so the renderer's PaneFeed can
  // stitch it to the replayed scrollback boundary with no gap and no duplication.
  onData: (cb) => ipcRenderer.on("pane:data", (_e, id, data, seq) => cb(id, data, seq)),
  onState: (cb) => ipcRenderer.on("shell:state", (_e, state) => cb(state)),
  onLayout: (cb) => ipcRenderer.on("shell:layout", (_e, plan) => cb(plan)),
  onLog: (cb) => ipcRenderer.on("shell:log", (_e, line) => cb(line)),
  // recovery (§15E .recovery): the reconstructed conductor-first layout (pinned CONDUCTOR pane 1 +
  // reattaching worker panes) plus interrupted sessions from a prior shell run — reported for
  // SUPERVISED relaunch, never auto-respawned. Live supervision state rides onState.recovery.
  onRecovery: (cb) => ipcRenderer.on("shell:recovery", (_e, info) => cb(info)),
  // conductor-first pane state (badge + succession control) pushed on launch/change.
  onConductor: (cb) => ipcRenderer.on("shell:conductor", (_e, state) => cb(state)),
  // Phase 17B `.spawn`: a WORKER pane's governed chrome, pushed whenever main revises it — today
  // when the session ends, so the badge stops reading `live` for a node that no longer exists
  // (invariant 27). Read-only, like every other stream here: the renderer draws what main sends.
  onPaneChrome: (cb) => ipcRenderer.on("pane:chrome", (_e, id, chrome) => cb(id, chrome)),
  // approval-queue drawer model (badge + rows) pushed on launch/change.
  onApprovals: (cb) => ipcRenderer.on("shell:approvals", (_e, model) => cb(model)),
  // Phase 17C `.probe` (U74): the voice-IN state, pushed when the ASYNCHRONOUS STT probe settles (and
  // after a capture). Without this the "probing…" badge would sit there until the operator clicked
  // something — the probe answers on its own schedule, so the chrome must be told, not polled.
  onVoice: (cb) => ipcRenderer.on("shell:voice", (_e, state) => cb(state)),
});
