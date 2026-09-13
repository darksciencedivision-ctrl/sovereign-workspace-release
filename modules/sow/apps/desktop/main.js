"use strict";
const { defaultPython, defaultPythonArgs } = require("./python-runtime");
/**
 * Sovereign desktop shell — Electron main process (PRODUCT code, Phase 14A).
 *
 * This is NOT the throwaway Phase-1 spike (tools/spike_compositor). It is the real workspace
 * shell: it owns supervised ConPTY sessions through the tested terminal/ modules, holds the
 * authoritative pane/window state (terminal/compositor/pane-model), and reaches the control
 * plane ONLY over the authenticated loopback IPC (D-IPC-01). The renderer is a thin view with
 * no Node access (contextIsolation on, nodeIntegration off, invariant 29 / TB-2).
 *
 * One-command operator run (like the spike): `npm install && npm start`. If IPC_PORT/IPC_TOKEN/
 * IPC_KEY are already in the environment the shell uses them; otherwise it spawns the Python
 * gateway (py -3.12 -m control_plane.ipc.run_gateway) and reads the printed handshake, so the
 * whole governed chain (shell → IPC → control plane) comes up from a single command.
 *
 * GUI note (loop directive §6): the window itself cannot be verified in the headless build
 * session — it is an operator-run metric exactly like the Phase-1 spike. The governance-bearing
 * logic under it (session lifecycle, supervision/admission, pane state, the IPC contract) is
 * covered by headless tests in terminal/test and apps/desktop/test.
 */
const { app, BrowserWindow, ipcMain } = require("electron");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

/**
 * SWS-CORRECTIVE-01 C3. This module's writable state root - never inside the installation.
 *
 * The shell sets SOVEREIGN_WORKSPACE_STATE for every module it launches
 * (`shell/src/adapter.py`, STATE_ROOT_ENV), pointing at that module's own state directory, so
 * under the shell this is always defined and always agrees with what `shell/modules/sow.json`
 * declares in `runtime_writes`. The fallback mirrors `workspace_state_root()` in the same file
 * for a developer running the app directly, so neither path ever writes into the install tree
 * and neither depends on the installation being writable.
 */
function sowStateRoot() {
  const declared = (process.env.SOVEREIGN_WORKSPACE_STATE || "").trim();
  if (declared) return declared;
  const local = (process.env.LOCALAPPDATA || "").trim()
    || path.join(os.homedir(), "AppData", "Local");
  return path.join(local, "SovereignWorkspace", "sow");
}
// F-131. The governed node store (leases, node events, model probes, journal) is durable operator
// state. The shell passes SOVEREIGN_STORE_ROOT=${state_root}/store; honour it. The old
// REPO_ROOT/.sovereign_store both OVERRODE that with an in-install path and destroyed those
// "never deletable" records on an upgrade that replaces the install tree.
function sowStoreRoot() {
  const declared = (process.env.SOVEREIGN_STORE_ROOT || "").trim();
  if (declared) return declared;
  return path.join(sowStateRoot(), "store");
}
const { createMainProcessLogger, redactArgvForLog } = require("./main-process-logger");
const { SovereignControlServer } = require("./control/sovereign-control-server");
const { structuredProviderFailure } = require("./control/provider-readiness");
// U328 (unit 19.3): the ONLY system→pane write path. A trust/permission modal is a numbered menu
// whose answer is one carriage return, so the gate lives on the write rather than on its callers —
// nothing this shell sends can answer a modal on the operator's behalf (invariant 1, D-P18-13).
const {
  createPaneWriter, paneScreenFromWindow, paneProviderResolver,
} = require("./control/pane-writer");
// U329 (unit 19.4): worker readiness reads its signals in ONE order — exit code, then structured
// provider signals, then (only if neither answered) a BOUNDED screen window through
// `RingBuffer.sliceFrom()`. The state machine lives in the module because this file cannot be
// required in a test (U338), and a negative control that a healthy worker's transcript is never
// scraped is exactly the kind of property that has to be driven to be believed.
const { createScreenWindow, createWorkerReadiness } = require("./control/worker-readiness");
const { conductorAdmission, conductorDescriptorsAgree } = require("./control/conductor-admission");
// U335 (19.7): whether a task may be handed to a worker — pane state AND the node's own MCP evidence.
const { assignmentRefusal } = require("./control/assignment-gate");
const { createApplicationControl, normalizedProvider } = require("./control/application-control");
const { createConductorReadiness } = require("./control/conductor-readiness");
const { createOperationalState } = require("./control/operational-state");
const { sessionEstablished } = require("./control/sovereign-control-server");
const { observedReadinessEvidence } = require("./control/readiness-evidence");
const { buildRoundTripProbe, answerObserved } = require("./conductor/roundtrip-probe");

const { SessionManager } = require("../../terminal/conpty/session-manager");
const { PaneModel } = require("../../terminal/compositor/pane-model");
const { planLayout, LayoutScheduler } = require("../../terminal/compositor/tiling");
const { IpcClient } = require("./ipc/client");
const { IpcSupervisor } = require("./supervisor");
const { fetchInspectorModel } = require("./inspector/source");
const { fetchOperationalState } = require("./inspector/operational-source");
const { fetchStatusBarModelFromGovernor } = require("./statusbar/governor-source");
const { fetchPickerModel } = require("./picker/source");
const {
  fetchConductorSelectionFeed, unknownSelectionFeed, selectConductorPreference,
} = require("./conductor/source");
const { sourceConductorSpawnFeed, unavailableSpawnFeed } = require("./conductor/spawn-source");
const { sourceConductorDispatchFeed, unavailableDispatchFeed } = require("./conductor/dispatch-source");
const { sourceApprovalDrawerFeed, routeApprovalDecision, unavailableApprovalFeed } = require("./approvals/drawer-source");
// Phase 17D `.events`: the append-only record of what THIS session actually produced (finding F2).
const { SessionApprovalLog } = require("./approvals/session-events");
const { conductorBadge, conductorSuccessionControl } = require("../../terminal/compositor/conductor-pane");
const { conductorDispatchSummary } = require("../../terminal/compositor/conductor-dispatch");
const { delegateToPane, selectObjectiveRecipients } = require("./control/conductor-delegation");
// SW-CONDUCTOR-001 Phase 3: the conductor pane's MCP harness. `ollama run` is a REPL with no MCP
// client of its own — control/local-mcp-bridge.js is that client, shell-side, because the PTY is
// the only surface a REPL exposes. Wiring lives with the conductor lifecycle below.
const { createLocalMcpBridge, createLoopbackRequest } = require("./control/local-mcp-bridge");
const { retrieveAndDeliver, createAnswerTally } = require("./control/conductor-view");
const { runtimeJournal, createStore, configureJournalModelSource, startJournalSession } = require("./control/journal-runtime");
const { buildApprovalDrawer, summarizeApprovalDrawer } = require("../../terminal/compositor/approval-drawer");
const {
  voiceControl, voiceOutcomeBadge, summarizeVoice, voiceTurnIndicator,
} = require("../../terminal/compositor/voice-indicator");
const { sourceConductorVoiceFeed, unavailableVoiceFeed } = require("./voice/voice-source");
const { decideDelivery, buildCaptureResult } = require("./voice/deliver");
const { VoiceProbe } = require("./voice/probe");
const { CaptureStore, CaptureStoreError, redactCapturePaths } = require("./voice/capture-store");
const { SupervisorVoiceTurnAuthority } = require("./voice/turn-authority");
const { ConductorPolicyBytes } = require("./voice/policy-bytes");
const { advanceConductorSessionLifecycle } = require("./voice/conductor-session-lifecycle");
const {
  createReleaseRetryScheduler,
  createReleaseTargetStore,
  releaseOrSchedule,
} = require("./voice/conductor-release-retry");
const {
  shouldOperatorResumeVoiceTurn, isOperatorTypedKey, operatorKeyKind,
} = require("./voice/operator-resume");
const { RecoveryStore } = require("./recovery-store");
const { resizePane, refusalWorthLogging } = require("./panes/resize-intent");
/** `paneId:reason` pairs already reported, so a continuously-fitting renderer logs each fault once. */
const resizeRefusalsLogged = new Set();
const { buildLayoutSnapshot, reconstructLayout, resumePaneSeq } = require("../../terminal/recovery/layout-reconstruct");
const { runPaneIoSelfCheck } = require("./selfcheck/pane-io-selfcheck");
const { runPickerSelfCheck } = require("./selfcheck/picker-selfcheck");
// Phase 18B `.picker` (OP-12): the two new providers in the REAL shell — groups, honest grey,
// provider-correct refusal text, governed selection, per-provider status-bar ceiling (D-P16-0).
const { runOp12PickerSelfCheck } = require("./selfcheck/op12-picker-selfcheck");
// Phase 18C `.close` (D-P16-0): the OP-12 acceptance receipt — the fail-closed world §17 prescribes
// a skip-with-record for, measured rather than asserted.
const { runOp12AcceptanceSelfCheck } = require("./selfcheck/op12-acceptance-selfcheck");
const { runOp18dRegistrationSelfCheck } = require("./selfcheck/op18d-registration-selfcheck");
// Phase 18E `.live.electron`: the LIVE per-provider acceptance leg (OP-12.2, directive §17.2(1)) —
// the sibling of `op12-acceptance` for the world whose switch is OPEN.
const { runOp12LiveAcceptanceSelfCheck } = require("./selfcheck/op12-live-acceptance-selfcheck");
const { runConductorSelfCheck } = require("./selfcheck/conductor-selfcheck");
const { runConductorSpawnSelfCheck } = require("./selfcheck/conductor-spawn-selfcheck");
const { runConductorDispatchSelfCheck } = require("./selfcheck/conductor-dispatch-selfcheck");
const { runStatusBarSelfCheck } = require("./selfcheck/statusbar-selfcheck");
const { runApprovalsSelfCheck } = require("./selfcheck/approvals-selfcheck");
const { runRecoverySelfCheck } = require("./selfcheck/recovery-selfcheck");
const { runVoiceSelfCheck } = require("./selfcheck/voice-selfcheck");
const { runVoiceProbeSelfCheck } = require("./selfcheck/voice-probe-selfcheck");
const { runVoiceMicSelfCheck } = require("./selfcheck/voice-mic-selfcheck");
// Phase 17C `.close`: real speech → real Parakeet → the bridge → pane 1's LIVE conductor session → an
// answer from the model. The leg `.mic` could not claim (its delivery pane was a stand-in).
const { runVoiceConductorSelfCheck } = require("./selfcheck/voice-conductor-selfcheck");
const { runAssembledSelfCheck } = require("./selfcheck/assembled-selfcheck");
// Phase 17A `.lease`: the governed LAUNCH TICKET + durable I-X3 lease check (D-P16-0, in-runtime).
const { runConductorLaunchSelfCheck } = require("./selfcheck/conductor-launch-selfcheck");
// Phase 17A `.pty`: the shell EXECUTES that ticket in pane 1's ConPTY (the end of the black pane).
const { runConductorPtySelfCheck } = require("./selfcheck/conductor-pty-selfcheck");
const { runConductorRoundTripSelfCheck } = require("./selfcheck/conductor-roundtrip-selfcheck");
const { runWorkerLaunchSelfCheck } = require("./selfcheck/worker-launch-selfcheck");
// Phase 17B `.spawn`: the shell EXECUTES a worker launch ticket in the pane's ConPTY (closes U70's
// spawn half) — the launcher is its own injectable module so every rule is headless-testable.
const { runWorkerSpawnSelfCheck } = require("./selfcheck/worker-spawn-selfcheck");
// Phase 17D `.close` (U73/U69): the pane-guard receipt — the sessionless placeholder's resize, and
// the physical-keystroke micro-link attempted and recorded rather than assumed.
const { runPaneGuardsSelfCheck } = require("./selfcheck/pane-guards-selfcheck");
// Phase 19 unit 19.3 (U328): the system→pane write gate, exercised against the REAL bindings this
// file builds — the headless suite drives the module with doubles and cannot see this wiring.
const { runSystemPaneWriteSelfCheck } = require("./selfcheck/system-pane-write-selfcheck");
// Phase 19 unit 19.4 (U329): the readiness WINDOW and the ORDER of its signals, measured in the
// packaged runtime against the audited whole-buffer read on the same live pane.
const { runReadinessWindowSelfCheck } = require("./selfcheck/readiness-window-selfcheck");
const { runConductorDescriptorSelfCheck } = require("./selfcheck/conductor-descriptor-selfcheck");
const { runRuntimeHonestySelfCheck } = require("./selfcheck/runtime-honesty-selfcheck");
const {
  runOrchestrationCollaborationSelfCheck,
} = require("./selfcheck/orchestration-collaboration-selfcheck");
// Phase 17E: the fully-live ASSEMBLED composition — every DONE leg true in one runtime.
const { runFullyLiveSelfCheck } = require("./selfcheck/fully-live-selfcheck");
const { createWorkerPaneLauncher } = require("./picker/worker-spawn");
// The worker-pane wiring RULES (post-spawn rollback, ended-chrome revision, the conductor-pane
// guard) — extracted from this file so the headless suite can drive them (spec-audit MAJOR-2).
const { endedWorkerChrome, createGovernedPaneSpawn, refuseSelection } = require("./picker/pane-wiring");
const {
  sourceConductorModelProbe, describeProbe, unprobed: unprobedModelProbe,
  modelProbeStrategy, unprobedDescriptorResult,
} = require("./conductor/model-probe-source");
const {
  sourceConductorLaunchTicket, releaseConductorLeaseSession,
  scrubbedLaunchEnv, scrubCredentialEnv, credentialNamesIn, ticketScrubLeftovers,
} = require("./conductor/launch-source");

// The operator's current conductor SELECTION + succession affordance, SOURCED from the ONE Python
// authority (control_plane/conductor/selection.OPERATOR_SELECTED_CONDUCTOR +
// conductor_pane_spawn.conductor_succession_affordance) via a bounded read-source
// (apps/desktop/conductor/source → tools/live/emit_conductor_selection --emit-conductor-selection),
// exactly as the 16B picker sources its options. This CLOSES U65: the shell no longer keeps a
// hand-maintained literal that could drift from the operator's authority — it renders what Python
// holds. The badge shows the SELECTION label (fable-5); the EXECUTING checkpoint stays unverified
// until a live reply reports one (invariant 3). Fail-closed: until sourced, or on any enumeration
// fault, the feed is the UNKNOWN feed and the badge renders "(unknown selection)" — never a fabricated
// model. The governed interactive launch (argv/env/live gates) is produced Python-side by
// conductor_pane_spawn.spawn_conductor_pane; the actual live `claude` ConPTY drive + the on-launch
// spawn wiring are the later 16C `.spawn`/`.dispatch` sub-steps, so the default shell still opens the
// pinned pane 1 in an honest "awaiting_live_conductor" state.
let conductorFeed = { ok: false, feed: unknownSelectionFeed() };
async function sourceConductorFeed() {
  conductorFeed = await fetchConductorSelectionFeed({ cwd: REPO_ROOT });
  if (!conductorFeed.ok) {
    log(`conductor: selection feed unavailable (fail-closed — badge shows unknown, no fabricated model): ${conductorFeed.error}`);
  }
  return conductorFeed;
}
function conductorSelectionRecord() { return conductorFeed.feed.selection_record; }
function conductorSuccessionAffordance() { return conductorFeed.feed.succession; }
function conductorDescriptor() {
  const d = conductorFeed.feed && conductorFeed.feed.conductor_descriptor;
  return d && d.role === "conductor" ? d : null;
}
function conductorModelLabel() {
  const d = conductorDescriptor();
  if (d && typeof d.display_name === "string" && d.display_name.trim()) return d.display_name.trim();
  const s = (conductorSelectionRecord() || {}).selection || {};
  return typeof s.model === "string" && s.model.trim() ? s.model.trim() : null;
}

// Phase 16C `.spawn`: pane 1 is GOVERNED-BORN through the Python governed spawn path
// (conductor_pane_spawn.spawn_conductor_pane) — the full live-gate chain (LIVE_OPERATION_AUTHORIZED +
// provider-live + R8 §6 operator terms + `claude` CLI presence + the I-X3 SubscriptionGovernor),
// exactly as a live worker pane. The shell SOURCES that governed spawn from the bounded emitter
// (apps/desktop/conductor/spawn-source → tools/live/emit_conductor_spawn --emit-conductor-spawn) so
// pane 1's `node_state` is no longer a hardcoded string — it is what the governed path produced. The
// emitter runs the spawn with NO launcher (the interactive `claude` ConPTY drive is the operator-run
// surface, directive §6) ⇒ the honest `awaiting_live_conductor` state (gates passed, argv +
// credential-scrubbed env built, I-X3 counted then RELEASED — D-LOOP-1), and tears the terminal down
// before emitting. Fail-closed: until sourced, or on any fault, the feed is the UNAVAILABLE feed and
// the conductor pane is an honest un-governed-live placeholder (spawned:false) — never a fabricated
// governed birth. A governed REFUSAL Python emits (e.g. live not authorized) is surfaced as-is.
let conductorSpawn = { ok: false, feed: unavailableSpawnFeed() };
async function sourceConductorSpawn() {
  conductorSpawn = await sourceConductorSpawnFeed({ cwd: REPO_ROOT });
  if (!conductorSpawn.ok) {
    log(`conductor: governed spawn feed unavailable (fail-closed — pane 1 shown un-governed-live, no fabricated spawn): ${conductorSpawn.error}`);
  } else if (!conductorSpawn.feed.spawned) {
    log(`conductor: governed spawn REFUSED (fail-closed): ${conductorSpawn.feed.reason}`);
  } else {
    log(`conductor: pane 1 GOVERNED-BORN via spawn_conductor_pane — node_state=${conductorSpawn.feed.node_state}, I-X3 released=${conductorSpawn.feed.governor_released} (D-LOOP-1)`);
  }
  return conductorSpawn;
}
// The governed spawn's node_state (sourced), or the fail-closed placeholder state. When the pane has
// not been created yet the shell reports "unstarted".
function conductorSpawnNodeState() {
  if (!conductorPaneId) return "unstarted";
  // Phase 17A `.pty`: once a LIVE interactive session is running in pane 1, that is the node state —
  // `awaiting_live_conductor` was only ever honest while nothing had been launched. Every other
  // launch state is reported as itself (refused / failed / unavailable), never dressed up.
  if (conductorLaunch.state === "running") return "live_conductor_running";
  if (conductorLaunch.state === "launching") return "launching_live_conductor";
  if (conductorLaunch.state === "refused") return "launch_refused";
  if (conductorLaunch.state === "failed") return "launch_failed";
  if (conductorLaunch.state === "exited") return "live_conductor_exited";
  const f = conductorSpawn.feed || {};
  return typeof f.node_state === "string" && f.node_state.length > 0 ? f.node_state : "unstarted";
}
// True iff pane 1 was born through the governed spawn path this launch (spawned:true), not the
// fail-closed placeholder. Surfaced so observability/self-checks can prove the node_state is sourced.
function conductorSpawnGoverned() { return conductorSpawn.ok === true && conductorSpawn.feed.spawned === true; }
// The governed spawn's chrome subscription view {ref,in_use,allowance} (I-X3 n/2), or null.
function conductorSpawnSubscription() {
  const ch = (conductorSpawn.feed || {}).chrome;
  return ch && ch.subscription ? ch.subscription : null;
}

// Phase 16C `.dispatch`: the govern-born conductor DISPATCHES work to worker nodes over MCP and
// synthesizes their gated results (OP-8 §13.4). tools/live/emit_conductor_dispatch runs ONE governed
// dispatch through the REAL live_flow loop (decompose → assign BY DESCRIPTOR → CANDIDATE → gates →
// synthesis) MOCK-first (no live model call, §2.2/§2.4), tears the loopback MCP server down (D-LOOP-1),
// and prints the folded conductor_dispatch_feed@1.0. Sourced via apps/desktop/conductor/dispatch-source.
// This proves the governed dispatch MACHINERY end-to-end and wires it into the shell; the LIVE worker
// leg stays honestly OWED (U58) — the actual live worker publication is the operator-run 16F run.
// Fail-closed: an unavailable/malformed feed renders "dispatch unavailable", never a fabricated dispatch.
let conductorDispatch = { ok: false, feed: unavailableDispatchFeed() };
async function sourceConductorDispatch() {
  conductorDispatch = await sourceConductorDispatchFeed({ cwd: REPO_ROOT });
  if (!conductorDispatch.ok) {
    log(`conductor: dispatch feed unavailable (fail-closed — dispatch shown unavailable, no fabricated dispatch): ${conductorDispatch.error}`);
  } else if (!conductorDispatch.feed.dispatched) {
    log(`conductor: governed dispatch did not run (fail-closed): ${conductorDispatch.feed.reason}`);
  } else {
    const f = conductorDispatch.feed;
    log(`conductor: governed DISPATCH ran (mock-first) — ${f.assigned_count} worker(s) by descriptor, ${f.accepted_count} accepted, legs ${f.legs.conductor}/${f.legs.workers}, live workers OWED (U58); torn_down=${f.torn_down} (D-LOOP-1)`);
    // Phase 17D `.events`, deliberately NOT recorded as an approval: a gate promotion belongs in the
    // operator's drawer, but THIS dispatch is the launch-time demonstration of the dispatch machinery
    // over the emitter's own fixed smoke objective — nobody asked for it. Putting it in the drawer
    // would recreate finding F2 one layer down: a plan awaiting approval on every launch that the
    // operator never requested. `sessionApprovals.recordDispatchPlan(feed, {operatorObjective:true})`
    // is the path for a plan the conductor decomposed from an objective the OPERATOR gave; it is
    // wired and covered (apps/desktop/test/session-events.test.js) and refuses anything else, and the
    // operator-driven dispatch that will call it lands with the conductor conversation (17E/OP-8 §13).
  }
  return conductorDispatch;
}
// True iff the conductor ran a governed dispatch this launch (dispatched:true), sourced from Python —
// surfaced so observability/self-checks can prove the dispatch line is sourced, not a literal.
function conductorDispatchRan() { return conductorDispatch.ok === true && conductorDispatch.feed.dispatched === true; }

let conductorPaneId = null; // the pinned pane-1 conductor node (OP-8 §13 / §12.4 conductor-first)

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const IS_WIN = process.platform === "win32";
const NODE_ID = process.env.SOVEREIGN_IPC_NODE || "shell";
// Plan §10.2 visible cap. The layout POLICY (planLayout) takes maxVisible as a parameter and is
// tunable; the shell currently pins the product cap of 8. Exposing an operator control to
// retune it live is deferred to the settings/approval surface (later 14A sub-step).
const MAX_VISIBLE = 8;

let win = null;
let gatewayProc = null;
let supervisor = null;
let manager = null;
let ipcClient = null;   // the authenticated loopback client; the read-only inspector rides it
let sovereignControl = null; // standard MCP tools -> authenticated app-control operations
const pendingSessionReleases = new Set();

function trackSessionRelease(promise, label) {
  if (!promise || typeof promise.then !== "function") return null;
  const tracked = Promise.resolve(promise)
    .catch((error) => {
      log(`${label} terminal reconciliation failed: ${error && error.message ? error.message : error}`);
      return { released: false, error: String(error && error.message ? error.message : error) };
    })
    .finally(() => pendingSessionReleases.delete(tracked));
  pendingSessionReleases.add(tracked);
  return tracked;
}

async function waitForSessionReleases(timeoutMs = 15000) {
  const pending = [...pendingSessionReleases];
  if (pending.length === 0) return { complete: true, pending: 0 };
  let timer = null;
  const completed = await Promise.race([
    Promise.allSettled(pending).then(() => true),
    new Promise((resolve) => { timer = setTimeout(() => resolve(false), timeoutMs); }),
  ]);
  if (timer) clearTimeout(timer);
  return { complete: completed && pendingSessionReleases.size === 0, pending: pendingSessionReleases.size };
}
const mainProcessLogger = createMainProcessLogger({
  file: process.env.SOW_MAIN_LOG_FILE
    || path.join(app.getPath("userData"), "logs", "main-process.log"),
  // W-35: the env override is validated, and a refused one falls back to the app's own path with
  // the refusal RECORDED rather than absorbed — a log silently going somewhere else is the failure
  // mode that hides every other one.
  fallbackFile: path.join(app.getPath("userData"), "logs", "main-process.log"),
  onPathRefused: (why) => {
    process.stderr.write(`[shell] SOW_MAIN_LOG_FILE refused (it ${why}); using the default log\n`);
  },
  rendererSink: (line) => {
    if (win && !win.isDestroyed()) win.webContents.send("shell:log", line);
  },
});
// Phase 17C `.close-revalidate2`: direct voice CHAT gets authority from this long-lived main-process
// service. The vendor hook is only an authenticated fail-closed transport to it.
// Phase 17C `.disarm` (U166): the restriction is now a state with an END, and the operator has to be
// able to SEE it (invariant 27). A turn is admitted by a socket callback — nothing the renderer asked
// for — so the chrome is pushed from here rather than polled.
// Phase 17C `.disarm-authority` (U181): the pinned hook and the module it requires both live inside
// the conductor's own cwd, so their launch-time hashes say nothing about the transport that just
// called. Re-read at DISPATCH, fail closed. The paths are the two files that ARE the boundary — the
// hook the ticket points the CLI at, and the module that hook requires.
const conductorPolicyBytes = new ConductorPolicyBytes({
  files: [
    path.join(REPO_ROOT, "tools", "live", "voice_turn_boundary.js"),
    path.join(__dirname, "voice", "turn-authority.js"),
  ],
});
function verifyConductorPolicyBytes() { return conductorPolicyBytes.verify(); }
const conductorVoiceAuthority = new SupervisorVoiceTurnAuthority({
  log: (m) => log(m),
  onChange: () => pushVoice(),
  verifyPolicy: () => verifyConductorPolicyBytes(),
});
let lastPickerModel = null; // last host-enumerated picker model (Phase 16B), cached for the chrome preview
let layoutSched = null; // membership-gated, 250 ms-debounced §10.2 relayout
const panes = new PaneModel();
// Per-session monotonic data-chunk sequence (Phase 16A). Every `pane:data` chunk is tagged with
// its seq so the renderer's PaneFeed can stitch byte-exact scrollback to the live stream with no
// gap and no duplication (the snapshot boundary is exact). Read atomically with the scrollback
// snapshot in the pane:scrollback handler (single-threaded main loop ⇒ consistent).
const dataSeq = new Map(); // paneId -> last emitted chunk seq
// Renderer-loaded gate: resolves when the window finishes loading, so the optional in-Electron
// self-check (SHELL_SELFCHECK) can drive the renderer only once it is ready.
let rendererReadyResolve = null;
const rendererReady = new Promise((res) => { rendererReadyResolve = res; });
// Durable session-lifecycle log for cross-restart reconstruction (directive §9 track 14A).
// In-repo, gitignored; the fold that reads it (terminal/recovery/reconstruct) is headless-tested.
// Under SHELL_SELFCHECK the store is isolated to a sibling subdir so the diagnostic run never
// pollutes the operator's real recovery state (its throwaway pane would otherwise resurface as an
// "interrupted session needing relaunch" on the next real launch).
// F-131. Recovery state (session log + layout snapshot) is operator state, not product bytes; it
// belongs in the shell-declared state root (sow.json declares ${state_root}/.recovery), never in
// the install tree. Under a per-machine install (Program Files) __dirname is not writable, so the
// previous __dirname/.recovery silently lost recovery across restarts.
const RECOVERY_DIR = path.join(sowStateRoot(), ".recovery", process.env.SHELL_SELFCHECK ? "selfcheck" : ".");
const recoveryStore = new RecoveryStore({ file: path.join(RECOVERY_DIR, "session-log.json"), log: (m) => log(m) });

// ---- conductor-first layout recovery (Phase 15E `.recovery`) ------------------
// Directive §9 track 14A ("UI recovery after process restart") + OP-7 §12.4 (conductor-first):
// besides the session log, the shell persists the pane-LAYOUT snapshot (order, roles, models,
// attended/autonomous, pinned) so a full restart rebuilds the pinned CONDUCTOR pane 1 and surfaces
// the worker panes reattaching. The fold (terminal/recovery/layout-reconstruct) is headless-tested;
// this is the operator-run wiring (§6). Fail-closed throughout: no worker is auto-respawned
// (invariant 2), nothing is admitted until the channel re-verifies.

// The operator conductor SELECTION in the fold's {model, verified, isFallback} shape (invariant 3 —
// the recovered CONDUCTOR badge shows the SELECTION label, never a guessed executing checkpoint).
function conductorSelection() {
  const rec = conductorSelectionRecord() || {};
  const sel = rec.selection || {};
  const exec = rec.executing || {};
  return { model: sel.model, verified: exec.verified === true, isFallback: exec.is_fallback === true };
}

// Per-pane governed CHROME the PaneModel does not itself hold (which model/role a worker pane runs,
// attended vs autonomous, its badge). The conductor pane carries its own chrome; worker panes get
// theirs from the live node-launcher picker — a governed selection RECORDED here per paneId (Phase
// 16D `.recovery`, closes U68). A pane with no recorded selection still snapshots honestly as role
// "worker" / model null (invariant 3 — never a fabricated model). The live governed worker SPAWN
// remains owed to 16F/U70; this is the record/read half so a restart repaints the exact badge.
const paneChrome = new Map(); // paneId -> the governed chrome preview (from spawnFromSelection)

function paneMeta(id) {
  if (id === conductorPaneId) return { role: "conductor", mode: "attended", model: conductorModelLabel() };
  const c = paneChrome.get(id);
  if (c) return { role: c.role, mode: c.mode, model: c.model_label, nodeId: c.model_slug || null, chrome: c };
  return {};
}

// Capture + persist the conductor-first layout snapshot (best-effort atomic write; never breaks a
// pane). Called at every structural change (pane create/destroy/pin, conductor create, session
// lifecycle) so the LAST GOOD layout is always on disk for the next boot.
function persistLayoutSnapshot() {
  try { recoveryStore.persistLayout(buildLayoutSnapshot({ panes, conductorPaneId, meta: paneMeta })); }
  catch (e) { log(`layout snapshot skipped (non-fatal): ${e.message}`); }
}

// Fold the persisted layout snapshot + reconstructed session view + current admission state into
// the conductor-first layout the shell rebuilds after a restart. Pure fold; the admission state is
// read from the live supervisor (false until the channel re-verifies ⇒ nothing admitted).
function reconstructConductorFirstLayout() {
  return reconstructLayout({
    snapshot: recoveryStore.loadLayout(),
    sessions: recoveryStore.loadAll(),
    admissionOpen: supervisor ? supervisor.ready : false,
    selection: conductorSelection(),
  });
}

// Reconstruct + push the conductor-first layout to the renderer over the SAME `shell:recovery`
// channel bootstrap uses on boot (the production restart path — no test-only shortcut). Returns the
// reconstructed layout. Used by the `.recovery` in-Electron self-check to drive a simulated restart.
function sendRecovery() {
  const recovered = reconstructConductorFirstLayout();
  if (win && !win.isDestroyed()) win.webContents.send("shell:recovery", { layout: recovered, interrupted: recoveryStore.loadInterrupted() });
  return recovered;
}

function log(msg) {
  return mainProcessLogger.log(msg);
}

// ---- gateway resolution (env, else spawn the real Python gateway) ------------
function resolveGateway() {
  if (process.env.IPC_PORT && process.env.IPC_TOKEN && process.env.IPC_KEY) {
    return Promise.resolve({
      port: Number(process.env.IPC_PORT), token: process.env.IPC_TOKEN, key: process.env.IPC_KEY, spawned: false,
    });
  }
  return new Promise((resolve, reject) => {
    // Role "shell", NOT "operator": the shell must not self-mint the highest role even
    // where it is currently unenforced (invariant 1 — the app never self-authorizes; the
    // operator holds final authority). The bootstrap credential is a diagnostic loopback
    // channel only; ordinary node credentials are issued by Sovereign at spawn.
    const proc = spawn(defaultPython(), [...defaultPythonArgs(), "-m", "control_plane.ipc.run_gateway"], {
      cwd: REPO_ROOT,
      env: { ...process.env, SOVEREIGN_IPC_NODE: NODE_ID, SOVEREIGN_IPC_ROLE: "shell", SOVEREIGN_IPC_PROJECT: "proj" },
    });
    gatewayProc = proc;
    const vals = {};
    let buf = "";
    const to = setTimeout(() => reject(new Error("gateway handshake timed out")), 15000);
    proc.stdout.on("data", (d) => {
      buf += d.toString();
      for (const line of buf.split(/\r?\n/)) {
        const m = /^(IPC_PORT|IPC_TOKEN|IPC_KEY)=(.+)$/.exec(line.trim());
        if (m) vals[m[1]] = m[2];
      }
      if (vals.IPC_PORT && vals.IPC_TOKEN && vals.IPC_KEY) {
        clearTimeout(to);
        resolve({ port: Number(vals.IPC_PORT), token: vals.IPC_TOKEN, key: vals.IPC_KEY, spawned: true });
      }
    });
    proc.stderr.on("data", (d) => log(`[gateway] ${String(d).trim()}`));
    proc.on("error", (e) => { clearTimeout(to); reject(e); });
    proc.on("exit", (code) => log(`gateway process exited (${code})`));
  });
}

// ---- node-pty session wiring -------------------------------------------------
// The LAST spec node-pty was actually handed, recorded at the real boundary so an in-runtime check
// can assert what the CHILD was given rather than what the ticket said (§2.2: KEY NAMES only — no
// value is ever recorded, logged or written to a receipt).
let lastPtySpawn = null;
function ptySpawnObserved() { return lastPtySpawn; }

function ptyFactory(spec) {
  const pty = require("node-pty"); // required lazily so headless tests never load the native addon
  // G20/S-11: a terminal is a session container. There is NO implicit shell default
  // here any more - a PTY exists only after the operator selects an execution type
  // that carries one. A pane without an execution type stays EMPTY (no process).
  if (!spec.file) {
    throw new Error("no-execution-type: pane stays EMPTY until an execution type is selected");
  }
  const file = spec.file;
  const env = spec.env || { ...process.env };
  const cwd = spec.cwd || os.homedir();
  lastPtySpawn = { file, args: (spec.args || []).slice(), cwd, envKeys: Object.keys(env).sort(),
    inheritedEnv: !spec.env };
  return pty.spawn(file, spec.args || [], {
    name: "xterm-256color", cols: spec.cols || 100, rows: spec.rows || 30,
    // Phase 17A `.pty`: a GOVERNED launch carries its own workspace (`cwd`) and its own
    // credential-SCRUBBED environment (§2.2) from the launch ticket — the child must not inherit
    // this shell's env verbatim, and must not start in whatever directory the shell happened to be
    // in. An ordinary local terminal pane (no spec.env) keeps the previous inherit-everything
    // behaviour: it is the operator's own shell, not a governed model session.
    cwd, env, useConpty: true,
  });
}

/**
 * The ONLY fields a renderer may set on a new pane. W-29: this was a DENY-list that dropped `env`
 * and `cwd` and let everything else through — so `file` and `args` reached `pty.spawn(file, args)`
 * and the RENDERER chose what the host executed. The review's §13.5(b) is why that is the
 * highest-leverage desktop fix: `session-manager.js:69` creates the OS process and
 * `supervisor.admit(...)` is not reached until `:101`, so a renderer-chosen executable is launched
 * first and judged second, and a denial can only try to kill something already running. An
 * allow-list is the one place the choice can be refused before a process exists.
 *
 * An allow-list rather than more deletions, deliberately: with a deny-list every field added to a
 * spec in future is permitted by default, and the missed field is found the way this one was.
 *
 * H-1 closure note (B3-1): `session-manager.js` now asks the supervisor for an admission verdict
 * BEFORE the PTY factory runs, so a renderer-chosen executable would be judged first even without
 * this allow-list. The allow-list stays as the stronger, earlier guarantee: the renderer never
 * names an executable at all, so there is nothing to judge.
 */
const RENDERER_SPEC_ALLOWED_KEYS = Object.freeze(["title", "cols", "rows"]);

/** Keep ONLY the fields a renderer is permitted to set. Pure. */
function sanitizeRendererSpec(spec) {
  const source = spec && typeof spec === "object" ? spec : {};
  const clean = {};
  for (const key of RENDERER_SPEC_ALLOWED_KEYS) {
    if (key in source) clean[key] = source[key];
  }
  const refused = Object.keys(source).filter((k) => !RENDERER_SPEC_ALLOWED_KEYS.includes(k));
  if (refused.length) {
    // KEY NAMES only (§2.2) — a refused value is never logged, and `env` values would be credentials.
    log(`pane:new — renderer-supplied ${refused.sort().join(", ")} REFUSED (allow-list: `
      + `${RENDERER_SPEC_ALLOWED_KEYS.join(", ")}; an executable and a governed environment come `
      + "from a launch ticket only)");
  }
  return clean;
}

let paneSeq = 0;
function createPaneWithSession(spec = {}) {
  // fail-closed: SessionManager.spawn throws SupervisionDenied if the control-plane channel
  // is not currently verified; the pane is only created for an admitted, supervised session.
  const id = `pane-${++paneSeq}`;
  manager.spawn({ id, nodeId: NODE_ID, spec });
  panes.createPane({ id, sessionId: id, title: spec.title || spec.file || "terminal" });
  persistLayoutSnapshot(); // capture the new pane structure for cross-restart recovery (§15E .recovery)
  pushState();
  emitLayoutNow(); // Phase 16A: create the pane's xterm view IMMEDIATELY (not only after the 250ms
  // relayout debounce) so the term exists close to spawn; scrollback replay covers any residual gap.
  return id;
}

function pushState() {
  if (!win || win.isDestroyed()) return;
  // Chrome/content push — restyle only, never a reflow (Plan §10.2). Session/focus/title/state
  // changes ride here; the grid geometry is a SEPARATE, debounced channel below.
  win.webContents.send("shell:state", {
    focusedId: panes.focusedId,
    maximizedId: panes.maximizedId,
    visible: panes.visible(),
    minimized: panes.minimized(),
    sessions: manager ? manager.registry.alive().map((s) => ({ id: s.id, state: s.state, pid: s.pid })) : [],
    supervised: supervisor ? supervisor.ready : false,
    // Observable recovery lifecycle (directive §9 track 14A): SUPERVISED | DEGRADED | RECOVERING
    // + the monotonic supervision epoch, so the renderer can show a truthful recovery banner.
    recovery: supervisor ? supervisor.supervisionState() : { state: "INIT", admissionOpen: false, epoch: 0 },
  });
  // Membership-gated relayout: only reflows the grid when the tiled/card membership actually
  // changes; chrome flips above leave the layout key unchanged and cost nothing here.
  if (layoutSched) layoutSched.update(panes.tilingMembers(), { maxVisible: MAX_VISIBLE });
}

// Compute + send the §10.2 layout plan immediately (used on first load, before the debounce).
function emitLayoutNow() {
  if (!win || win.isDestroyed()) return;
  win.webContents.send("shell:layout", planLayout(panes.tilingMembers(), { maxVisible: MAX_VISIBLE }));
}

// ---- conductor-first pane (Phase 15E .conductor-pane; OP-8 §13 / §12.4) ------
// The conductor pane opens as PANE 1 on launch, pinned (⇒ tiling P0, never auto-collapsed), labeled
// CONDUCTOR. The live interactive `claude` session + I-X3 governor + live gates are enforced
// Python-side (conductor_pane_spawn.spawn_conductor_pane); the actual ConPTY drive is operator-run
// (directive §6). Here the shell places the pinned pane-1 and renders its CONDUCTOR chrome; before a
// live launch it is honestly "awaiting_live_conductor" (no naked session is spawned).
function conductorState() {
  const descriptor = conductorDescriptor();
  const baseBadge = conductorBadge(conductorSelectionRecord());
  const liveDispatch = operationalDispatchSummary();
  const operationalNodeState = conductorLaunch.state === "running"
    ? (conductorLaunch.operationalState || "STARTING") : conductorSpawnNodeState();
  return {
    paneId: conductorPaneId,
    label: "CONDUCTOR",
    // Phase 16C `.spawn`: node_state is SOURCED from the governed spawn path (spawn_conductor_pane),
    // not a hardcoded string — "awaiting_live_conductor" when pane 1 was governed-born this launch,
    // else the fail-closed placeholder state ("unstarted" / "spawn_refused").
    nodeState: operationalNodeState,
    badge: {
      ...baseBadge,
      provider: descriptor && descriptor.provider_id,
      displayName: descriptor && descriptor.display_name,
      modelSlug: descriptor && descriptor.model_id,
      authentication: descriptor ? "provider preflight required" : "unknown",
      available: Boolean(descriptor),
      verified: baseBadge.verified === true || conductorLaunch.operationalState === "READY",
    },
    descriptor,
    succession: conductorSuccessionControl(conductorSuccessionAffordance()),
    subscription: conductorSpawnSubscription(),
    // Phase 17A `.pty`: the LIVE session in pane 1 — observable and honest in every state. `live`
    // is true ONLY while a supervised ConPTY session is genuinely registered and running; the badge
    // reads the SELECTION label as before (invariant 3 — a live process is not a verified
    // checkpoint; that is `.roundtrip`'s evidence to produce, not this one's to claim).
    launch: conductorLaunchState(),
    live: conductorLaunch.state === "running"
      && Boolean(manager && manager.registry && manager.registry.has(conductorPaneId)),
    // Phase 16C `.dispatch`: the governed dispatch summary (assignments BY DESCRIPTOR, accepted count,
    // legs verbatim, the OWED live-worker leg — U58), SOURCED from the governed dispatch feed. Pure
    // fold; the renderer draws one dispatch line from it. Fail-closed to "unavailable" (never fabricated).
    dispatch: liveDispatch || conductorDispatchSummary(conductorDispatch.feed),
    dispatchRan: Boolean(liveDispatch) || conductorDispatchRan(),
    dispatchSourced: Boolean(liveDispatch) || conductorDispatch.ok === true,
    dispatchReason: liveDispatch ? null : (conductorDispatch.feed || {}).reason || null,
    dispatchLegs: liveDispatch ? liveDispatch.legs : (conductorDispatch.feed || {}).legs || null,
    dispatchLiveWorkersOwed: liveDispatch ? null : (conductorDispatch.feed || {}).live_workers_owed || null,
    dispatchSource: liveDispatch ? "live_supervised_worker_registry"
      : conductorDispatch.ok
        ? "governed_python_dispatch (tools/live/emit_conductor_dispatch → live_flow)"
        : `fail_closed_unavailable (${conductorDispatch.error || "not yet sourced"})`,
    // U65: whether the badge was SOURCED from the authoritative Python emitter (true) or is the
    // fail-closed unknown feed (false). Surfaced so observability/self-checks can prove the badge is
    // sourced, not a hand-maintained literal; the renderer does not need it to draw the badge.
    selectionSourced: conductorFeed.ok === true,
    selectionSource: conductorFeed.ok
      ? "authoritative_python_emitter (tools/live/emit_conductor_selection)"
      : `fail_closed_unknown (${conductorFeed.error || "not yet sourced"})`,
    // Phase 16C `.spawn`: whether pane 1 was GOVERNED-BORN via spawn_conductor_pane this launch
    // (the full live-gate chain), and the source label. Load-bearing for the self-check: a reverted
    // hardcoded node_state would leave spawnGoverned false.
    spawnGoverned: conductorSpawnGoverned(),
    spawnSourced: conductorSpawn.ok === true,
    spawnRefused: conductorSpawn.ok === true && conductorSpawn.feed.spawned === false,
    spawnReason: (conductorSpawn.feed || {}).reason || null,
    spawnTornDown: (conductorSpawn.feed || {}).torn_down === true,
    spawnSource: conductorSpawn.ok
      ? "governed_python_spawn (tools/live/emit_conductor_spawn → spawn_conductor_pane)"
      : `fail_closed_unavailable (${conductorSpawn.error || "not yet sourced"})`,
  };
}

function createConductorPane() {
  if (conductorPaneId && panes.panes.has(conductorPaneId)) return conductorPaneId;
  const id = `pane-${++paneSeq}`;
  // A governed conductor node — created as the shell's own pinned pane-1 view, role "conductor". No
  // ConPTY session is spawned until the live interactive launch (operator-run); until then the pane
  // is an honest CONDUCTOR placeholder, not a naked model session (invariant 2/3).
  // Title sourced from the authoritative selection (U65); fail-closed to plain "CONDUCTOR" when the
  // model could not be sourced — never a fabricated "fable-5" the shell could not confirm.
  const label = conductorModelLabel();
  panes.createPane({ id, sessionId: null, title: label ? `CONDUCTOR · ${label}` : "CONDUCTOR" });
  panes.pin(id); // pinned pane-1 by default (§12.4) ⇒ tiling P0, always visible
  conductorPaneId = id;
  persistLayoutSnapshot(); // record the pinned CONDUCTOR pane-1 for cross-restart recovery (§15E .recovery)
  pushConductor();
  pushState();
  return id;
}

function pushConductor() {
  if (!win || win.isDestroyed()) return;
  win.webContents.send("shell:conductor", conductorState());
}

// ---- the LIVE conductor session in pane 1 (Phase 17A `.pty`; OP-11 §16 track 17A) -------------
// The operator's finding F3: pane 1 sat at `awaiting_live_conductor` — gates passed, no session,
// typing answered by nothing. `.lease` produced the missing shape (a governed launch TICKET with a
// durable I-X3 lease the shell holds). This is where the shell EXECUTES it.
//
// The chain, in order, with no step the shell can skip or invent:
//   1. Python decides. `sourceConductorLaunchTicket` runs the same gate chain 16C gated
//      (live_operation switch → provider-live → OP-9 terms → `claude` presence → I-X3, now durable)
//      and returns an interactive argv, the credential env NAMES to drop, the governed identity, the
//      bound workspace, and a HELD lease keyed to the session id THIS shell chose (U75).
//   2. The shell spawns it through the SUPERVISED path only — `SessionManager.spawn` refuses without
//      an admitted node (`IpcSupervisor.admit` over the verified control-plane channel), reports the
//      lifecycle, and kills every session if supervision is lost. No naked session (invariant 2).
//   3. A pre-birth failure after the lease was taken RELEASES it by session key (U77). A post-birth
//      rollback RETAINS it until the exact PID/generation exits.
//   4. Kill/quit signal termination; only confirmed process exit hands the lease back (D-LOOP-1).
//      If Electron exits first, dead-holder reaping covers the vanished owner independently.
/**
 * A millisecond interval from the environment, PARSED rather than coerced (U371, closed in unit
 * 19.4). `Number(process.env.X || 500)` answers `NaN` for a malformed override, `setTimeout(NaN)` is
 * 0 ms, and U364's echo-settle wait is expressed in POLLS of one of these intervals — so a typo did
 * not shorten a wait, it deleted it, which is mutation P13 (a system write goes from WITHHELD to
 * DELIVERED). A malformed or non-positive value takes the measured default and says so; it is not
 * silently obeyed and it is not fatal.
 */
function intervalMs(name, fallback) {
  const raw = process.env[name];
  if (raw === undefined || raw === null || String(raw).trim() === "") return fallback;
  const parsed = Number(String(raw).trim());
  if (!Number.isFinite(parsed) || parsed <= 0) {
    // `log()` is not built yet at module-evaluation time; this is the one channel that always is.
    console.error(`[main] ${name}=${JSON.stringify(raw)} is not a positive number of `
      + `milliseconds — using the default ${fallback} ms`);
    return fallback;
  }
  return parsed;
}

const CONDUCTOR_LAUNCH_TIMEOUT_MS = 120000;
const PROCESS_STARTUP_TIMEOUT_MS = intervalMs("SOVEREIGN_PROCESS_STARTUP_TIMEOUT_MS", 120000);
const MCP_READINESS_TIMEOUT_MS = intervalMs("SOVEREIGN_MCP_READINESS_TIMEOUT_MS", 120000);
const WORKER_TASK_SOFT_DEADLINE_MS = intervalMs("SOVEREIGN_WORKER_SOFT_DEADLINE_MS", 480000);
const WORKER_TASK_HARD_DEADLINE_MS = intervalMs("SOVEREIGN_WORKER_HARD_DEADLINE_MS", 600000);
const PEER_RESPONSE_DEADLINE_MS = intervalMs("SOVEREIGN_PEER_RESPONSE_DEADLINE_MS", 180000);
const DEBATE_TURN_DEADLINE_MS = intervalMs("SOVEREIGN_DEBATE_TURN_DEADLINE_MS", 180000);
const PROVIDER_PASTE_SETTLE_MS = intervalMs("SOVEREIGN_PROVIDER_PASTE_SETTLE_MS", 500);
const CODEX_SUBMIT_CONFIRM_MS = intervalMs("SOVEREIGN_CODEX_SUBMIT_CONFIRM_MS", 200);
let launchSeq = 0;
// Observable launch state (invariant 27): unstarted | launching | running | terminating |
// release_pending | release_failed | exited | refused | unavailable | failed. `refused` is a
// GOVERNED refusal (a gate said no, with a reason); `failed` is this shell's own inability to spawn
// what it was authorized to.
let conductorLaunch = {
  state: "unstarted", sessionId: null, leaseId: null, subscriptionRef: null, pid: null,
  sessionGeneration: null, nodeId: null, mcpState: "disconnected",
  argv: null, executable: null, cwd: null, envScrubNames: [], reason: null, startedAt: null,
  endedAt: null, exitCode: null,
  supervised: false, scrubbedCount: null,
  operationalState: "STARTING", readiness: null, structuredFailure: null,
  // WHERE the `--model` slug in `argv` came from (Phase 17A `.roundtrip`) — a recorded live probe,
  // a recorded CLI-default fallback, or "unprobed". Never silent (invariant 3, directive §11 15B).
  modelProbe: null,
};

function conductorLaunchState() { return { ...conductorLaunch }; }

// ---- the `--model` slug the host CLI actually accepts (Phase 17A `.roundtrip`) ----------------
// `.pty` launched with the operator's SELECTION LABEL as the slug, and the live session answered
// every prompt with "There's an issue with the selected model (fable-5). It may not exist or you may
// not have access to it." — a running session that could not answer. The shell now asks Python what
// the CLI accepts BEFORE it asks for a launch ticket: `probe_conductor_model.py` spends at most one
// minimal live call per candidate slug behind the same live gates, holds one durable I-X3 terminal
// while it runs, and caches the verdict on the host so every later launch is offline.
//
// Memoized ONLY for a decided answer. Caching an INCONCLUSIVE one (a timeout, a rate-limit, a
// refusal) for the life of the shell is exactly the F1 defect this phase was opened to fix — a
// single cold miss pinned for the app's lifetime — and the run it would pin is precisely the one
// that reverts to a conductor that cannot answer. An undecided probe is therefore forgotten, so the
// next launch attempt asks again.
//
// `SOW_CONDUCTOR_MODEL_PROBE=0` opts out of the live CALL, not of the recorded verdict: a slug the
// host already proved is still used (it is knowledge, not a call), and an unprobed host carries the
// operator's label verbatim exactly as before this existed. A probe that cannot decide NEVER
// demotes the selection.
const MODEL_PROBE_TIMEOUT_MS = 240000;
let conductorModelProbe = null;

/** Did the probe actually DECIDE (accepted slug or recorded fallback)? */
function probeDecided(res) {
  const r = (res && res.probe && res.probe.resolution) || {};
  return res && res.ok === true && (r.model_available === true || r.model_available === false);
}

function ensureConductorModelProbe() {
  const desc = conductorDescriptor();
  if (modelProbeStrategy(desc) !== "host_probe") {
    return Promise.resolve(unprobedDescriptorResult(desc));
  }
  if (process.env.SOW_CONDUCTOR_MODEL_PROBE === "0") {
    // still honors an already-recorded verdict — `--ledger-only` spends nothing
    return sourceConductorModelProbe({ cwd: REPO_ROOT, ledgerOnly: true, timeoutMs: 30000 })
      .then((res) => {
        log(`conductor: live model probe DISABLED (SOW_CONDUCTOR_MODEL_PROBE=0) — ${describeProbe(res.probe)}`);
        return res;
      })
      .catch((e) => ({ ok: false, probe: unprobedModelProbe(`probe disabled; ledger unreadable: ${e.message}`) }));
  }
  if (!conductorModelProbe) {
    conductorModelProbe = sourceConductorModelProbe({ cwd: REPO_ROOT, timeoutMs: MODEL_PROBE_TIMEOUT_MS })
      .then((res) => {
        log(`conductor: ${describeProbe(res.probe)}`);
        if (!probeDecided(res)) conductorModelProbe = null;  // undecided ⇒ ask again next launch
        return res;
      })
      .catch((e) => {
        conductorModelProbe = null;
        return { ok: false, probe: unprobedModelProbe(`model probe failed: ${e.message}`) };
      });
  }
  return conductorModelProbe;
}

/** Hand the durable terminal back for the session key we hold. Async, never throws. */
async function releaseConductorTerminal(sessionId, why) {
  if (!sessionId) return { released: false };
  const res = await releaseConductorLeaseSession(sessionId, { cwd: REPO_ROOT, timeoutMs: CONDUCTOR_LAUNCH_TIMEOUT_MS });
  log(`conductor: durable I-X3 terminal for ${sessionId} ${res.released ? "RELEASED" : "not released"} (${why})${res.error ? ` — ${res.error}` : ""}`);
  return res;
}

const conductorReleaseRetries = createReleaseRetryScheduler({
  retry: (sessionId) => reconcileConductorTerminalRelease(sessionId, "retry after release failure"),
});
const conductorReleaseTargets = createReleaseTargetStore();
function scheduleConductorReleaseRetry(sessionId) {
  conductorReleaseRetries.schedule(sessionId);
}

async function releaseConductorTerminalWithRetry(sessionId, why, targetState = null, targetReason = null) {
  if (targetState) conductorReleaseTargets.mark(sessionId, targetState, targetReason || why);
  const result = await releaseOrSchedule({
    sessionId,
    release: () => releaseConductorTerminal(sessionId, why),
    schedule: scheduleConductorReleaseRetry,
  });
  if (result && result.ok === true && targetState) conductorReleaseTargets.take(sessionId);
  return result;
}

async function reconcileConductorTerminalRelease(sessionId, why) {
  const res = await releaseConductorTerminal(sessionId, why);
  const target = res && res.ok === true ? conductorReleaseTargets.take(sessionId) : null;
  if (conductorLaunch.sessionId !== sessionId) return res;
  if (res && res.ok === true) {
    conductorLaunch = {
      ...conductorLaunch, state: (target && target.state) || "exited", leaseId: null,
      reason: `${(target && target.reason) || conductorLaunch.reason || "session exited"}; `
        + "durable terminal reconciled",
    };
  } else {
    conductorLaunch = {
      ...conductorLaunch, state: "release_failed",
      reason: `${conductorLaunch.reason || "session exited"}; terminal release failed `
        + `(${(res && res.error) || "unknown"})`,
    };
    scheduleConductorReleaseRetry(sessionId);
  }
  pushConductor();
  return res;
}

// ---- SW-CONDUCTOR-001 Phase 3: the LOCAL MCP BRIDGE wiring ---------------------------------------
// A local conductor pane runs `ollama run <tag>` — a chat REPL, not an agent. It has no MCP
// client, so no request ever arrived from it at the control gateway, connectionState stayed
// `configured` (a credential issued and nothing ever arrived), and conductor readiness gate 1
// (waitForNodeMcp) timed out on every launch — the measured STALLED badge. control/local-mcp-
// bridge.js is that pane's MCP harness, and this is its only wiring: ONE bridge per governed
// launch, bound to the node id the launch ticket minted, attached after the governed spawn
// succeeded and before readiness runs, detached on session end, on launch failure, and on quit.
//
// THE HONESTY BOUNDARY (standing rule 6, and the bridge module's own design): the bridge may make
// the ATTACHMENT claim on the node's behalf — the one `identity` call, which the control server
// deliberately does NOT record as an operation (sovereign-control-server.js) — but every tool call
// it relays is one the model actually emitted into the pane, read back through the SAME bounded
// window conductor delegation reads through (readinessWindow). It never synthesizes a call, never
// retries one the model did not make, and never relays after the session died. A mute model still
// STALLS with readiness's own honest reason: gate 2 counts server-recorded get_worker_status
// operations, and attachment cannot raise that count.
//
// Every byte the bridge writes into the pane (the preamble, result fences) goes through the
// U328-gated writePanePrompt — the bridge has no raw write path, and a gate that holds makes the
// bridge hold. The control token is a credential: it travels from the childEnv mint straight into
// the bridge instance and never into conductorLaunch, pushConductor state, or a log line.
let conductorBridge = null;
let conductorBridgeRun = null;

/** Handle-level session liveness — the same fact `manager.write` guards on. A registry record
 *  outlives its process (an ended session still answers `registry.has`), so liveness is: the
 *  record is still RUNNING AND this PTY generation has not confirmed exit. */
function conductorSessionAlive(paneId) {
  if (!manager || !paneId) return false;
  const session = manager.registry.has(paneId) ? manager.registry.get(paneId) : null;
  return Boolean(session && session.state === "RUNNING" && manager.processIdentity(paneId));
}

/** Attach a fresh bridge for THIS launch's node. Fail-closed: every refusal path logs honestly
 *  and returns false — readiness then produces its own STALLED verdict on its own reason, which
 *  is the pre-existing behavior for a conductor no request ever arrived from. */
async function attachConductorBridge(nodeId, token) {
  detachConductorBridge("a new conductor launch is attaching");
  if (!nodeId || !token) {
    log("conductor bridge: not attached — no ticket-minted node id or no control credential for it");
    return false;
  }
  if (!conductorPaneId || !sovereignControl || !sovereignControl.port) {
    log("conductor bridge: not attached — the conductor pane or the control gateway is unavailable");
    return false;
  }
  const bridge = createLocalMcpBridge({
    nodeId,
    paneId: conductorPaneId,
    port: sovereignControl.port,
    token,
    request: createLoopbackRequest(),
    sessionAlive: conductorSessionAlive,
    window: readinessWindow,
    writePrompt: writePanePrompt,
    writeRefusal: paneWriteRefusalFor,
    log,
  });
  let out = null;
  try {
    out = await bridge.attach();
  } catch (e) {
    log(`conductor bridge: attach failed for node ${nodeId}: ${e.message}`);
    return false;
  }
  if (!out || out.attached !== true) {
    log(`conductor bridge: NOT attached for node ${nodeId} — `
      + `${(out && out.reason) || "unknown reason"}; readiness will report its own verdict`);
    return false;
  }
  conductorBridge = bridge;
  const taught = await bridge.teach().catch((e) => {
    log(`conductor bridge: the preamble write failed: ${e.message}`);
    return false;
  });
  conductorBridgeRun = bridge.run({ pollMs: 500, heartbeatMs: 5000 });
  log(`conductor bridge: attached for node ${nodeId} on pane ${conductorPaneId}`
    + (taught === true
      ? "; preamble written through the gated writer"
      : "; preamble NOT written (the gated writer withheld or refused it) — the model was not "
        + "taught the fence grammar for this launch"));
  return true;
}

/** Idempotent detach: stop the poll loop (which detaches internally) and drop the instance.
 *  Never throws — it is called from session-end, launch-failure and teardown paths. */
function detachConductorBridge(why) {
  const bridge = conductorBridge;
  const run = conductorBridgeRun;
  conductorBridge = null;
  conductorBridgeRun = null;
  if (!bridge && !run) return false;
  const reason = why || "unspecified";
  try {
    if (run) run.stop(reason);
    else bridge.detach(reason);
  } catch { /* a teardown path must not fail on its own cleanup */ }
  log(`conductor bridge: detached (${reason})`);
  return true;
}

/**
 * Launch (or re-launch) the real interactive `claude` conductor session in pane 1's ConPTY.
 * Returns an observable result; never throws into a caller. One session at a time — the operator's
 * live session persists by design (directive §16 17A), so a second request while one is running is
 * refused, not silently duplicated.
 */
async function launchConductorSession({ reason = "operator control" } = {}) {
  // Every refusal below RECORDS its reason and pushes it, so the pane's control can say why it is
  // still dark — a silent no-op is the defect, not the refusal.
  const refuse = (why, state) => {
    conductorLaunch = { ...conductorLaunch, state: state || conductorLaunch.state, reason: why };
    log(`conductor: live launch not attempted — ${why}`);
    pushConductor();
    return { launched: false, reason: why };
  };
  if (!conductorPaneId) return refuse("the conductor pane does not exist yet (the window has not finished loading)");
  if (conductorLaunch.state === "launching") return refuse("a launch is already in flight");
  if (conductorLaunch.state === "running" && manager && manager.registry.has(conductorPaneId)) {
    return refuse("a live conductor session is already running in pane 1");
  }
  if (!supervisor || !supervisor.ready) {
    // invariant 2, stated the way the operator will read it in the banner: admission is SHUT, so
    // nothing is born. This is the fail-closed path, not an error.
    return refuse("supervision is not READY — a session is only ever born on a verified control-plane channel",
      "unavailable");
  }
  if (manager.registry.has(conductorPaneId)) {
    // A record from a session that already ENDED must not wedge pane 1 for the rest of the shell's
    // life: forget it (the append-only lifecycle log keeps the history) so the operator can relaunch
    // the conductor. The registry REFUSES to forget a live session, so this can never orphan a
    // supervised process.
    try {
      manager.forget(conductorPaneId);
      log(`conductor: cleared the ended session record for ${conductorPaneId} — relaunching`);
    } catch (e) {
      return refuse(`pane ${conductorPaneId} still carries a live session record (${e.message})`);
    }
  }

  const sessionId = `${conductorPaneId}#${process.pid}.${++launchSeq}`;
  conductorLaunch = {
    ...conductorLaunch, state: "launching", sessionId, leaseId: null, pid: null,
    sessionGeneration: null, reason: null,
    startedAt: new Date().toISOString(), endedAt: null, exitCode: null, supervised: false,
  };
  pushConductor();
  // Resolve the accepted `--model` slug FIRST (cached after the first run) so the ticket authorizes
  // a session that can actually answer. Its verdict reaches the ticket through the host probe
  // ledger, which the Python emitter reads offline — the shell decides nothing here.
  const probeRes = await ensureConductorModelProbe();
  conductorLaunch = { ...conductorLaunch, modelProbe: (probeRes.probe && probeRes.probe.resolution) || null };
  log(`conductor: requesting a governed launch ticket for session ${sessionId} (${reason})`);

  const res = await sourceConductorLaunchTicket({
    cwd: REPO_ROOT, holderPid: process.pid, sessionId, timeoutMs: CONDUCTOR_LAUNCH_TIMEOUT_MS,
  });
  const ticket = res.ticket || {};
  if (!res.ok) {
    // U77: the emitter may have taken the lease before the failure (a shape drift, a timeout) — the
    // shell never learned a lease id, but it chose the SESSION key, so it can still hand it back.
    const rel = await releaseConductorTerminalWithRetry(
      sessionId, "ticket undelivered", "unavailable", res.error,
    );
    const releaseFailed = !rel || rel.ok !== true;
    conductorLaunch = {
      ...conductorLaunch,
      state: releaseFailed ? "release_failed" : "unavailable",
      reason: releaseFailed
        ? `${res.error}; durable terminal release failed (${(rel && rel.error) || "unknown"})`
        : res.error,
      endedAt: new Date().toISOString(),
    };
    log(`conductor: launch ticket unavailable (fail-closed — pane 1 stays un-launched): ${res.error}`);
    pushConductor();
    return { launched: false, reason: res.error };
  }
  if (ticket.authorized !== true) {
    conductorLaunch = { ...conductorLaunch, state: "refused", reason: ticket.reason || "governed refusal", endedAt: new Date().toISOString() };
    log(`conductor: governed launch REFUSED (fail-closed, no session): ${conductorLaunch.reason}`);
    pushConductor();
    return { launched: false, refused: true, reason: conductorLaunch.reason };
  }

  const launch = ticket.launch || {};
  const identity = ticket.identity || {};
  const lease = ticket.lease || {};
  const argv = launch.argv.slice();
  try {
    if (!conductorDescriptorsAgree(ticket.conductor_descriptor, conductorDescriptor())) {
      throw new Error("launch ticket conductor descriptor disagrees with the current selection feed");
    }
    // The launch ticket pins the hook bytes/settings but honestly says the hook dispatcher itself is
    // not supervisor-process enforcement. Start the real authority service in THIS long-lived main
    // process, then inject only its ephemeral loopback capability into the supervised child. A
    // ticket cannot claim this runtime fact on its own.
    const isClaudeHookBoundary = ticket.authority_boundary
      && ticket.authority_boundary.schema === "voice_turn_boundary@1.0";
    let runtimeBoundary = ticket.authority_boundary || null;
    let env = scrubbedLaunchEnv(ticket, process.env);
    // ---- W-32 stage 2: the ticket-name leftover guard, which this path did not have -------------
    // The worker path has enforced this since 18B; the conductor path never did, so a defective
    // ticket scrub failed silently HERE and loudly there. Case-insensitive for the U105 reason:
    // Windows env names are case-insensitive to the OS while a plain-object delete is not.
    // It runs BEFORE the classifier below, deliberately — the classifier would otherwise remove the
    // very name this guard exists to catch and the fault would never be reported (operator ruling).
    const ticketLeftovers = ticketScrubLeftovers((launch.env_scrub_names || []), env);
    if (ticketLeftovers.length) {
      throw new Error(`the credential scrub left ${ticketLeftovers.length} ticket-named var(s) in `
        + `the conductor environment (${ticketLeftovers.sort().join(", ")}) — refusing to launch (§2.2)`);
    }
    // ---- W-32 stage 3: the classifier floor, not injectable ------------------------------------
    // Removes what no ticket declares: NODE_PATH / NODE_OPTIONS / NODE_EXTRA_CA_CERTS redirect or
    // inject into an npm-installed Node CLI, and the prefix/substring nets catch a credential the
    // ticket's author never listed. Applied before the shell mints this child's capabilities, so it
    // cannot delete the capability the launch is granting.
    env = scrubCredentialEnv(env);
    if (isClaudeHookBoundary) {
      await conductorVoiceAuthority.start();
      runtimeBoundary = conductorVoiceAuthority.runtimeBoundary(ticket.authority_boundary);
    if (!runtimeBoundary) {
      throw new Error("the supervisor-process voice authority could not bind the launch-ticket profile");
    }
    // U181 — take the policy-byte baseline for THIS launch, cross-checked against the hash the ticket
    // computed moments ago, before the child that can write to those files exists. Every hook dispatch
    // from here on is answered only if the bytes still match.
    const pinned = conductorPolicyBytes.pin({
      [path.join(REPO_ROOT, "tools", "live", "voice_turn_boundary.js")]:
        (ticket.authority_boundary && ticket.authority_boundary.hook_sha256) || null,
    });
    if (!pinned.ok) throw new Error(pinned.reason);
      env = conductorVoiceAuthority.childEnv(env);
    } else {
      conductorPolicyBytes.clear();
    }
    if (!sovereignControl || !sovereignControl.port) {
      throw new Error("Sovereign application-control MCP gateway is not ready");
    }
    // SW-CONDUCTOR-001 Phase 3: the mint returns { env, token } — the token is the node's own
    // bearer for the local MCP bridge attached after the spawn. It travels from this mint
    // straight into the bridge instance, never into observable launch state.
    const controlMint = sovereignControl.childEnv({
      node_id: identity.node_id, role: "conductor", project_id: "proj",
      provider_id: (ticket.conductor_descriptor || {}).provider_id || null,
      model_id: (ticket.conductor_descriptor || {}).model_id || null,
      pane_id: conductorPaneId, session_id: sessionId,
      store_root: sowStoreRoot(),  // F-131
    }, env);
    env = controlMint.env;
    // ---- W-32 stage 4: assert on the environment ACTUALLY handed to the child -------------------
    // Placed after BOTH minting steps (the voice authority above and the control server just now),
    // because stage 3 having run is not the same fact as the child being clean — that is the
    // "measured in the wrong process" half of this unit. The shell-minted capabilities are exempt
    // by name; anything else classifier-positive here got in behind the scrub.
    const classifiedLeftovers = credentialNamesIn(env);
    if (classifiedLeftovers.length) {
      // NAMES only (§2.2) — never a value, not even in a refusal.
      throw new Error(`${classifiedLeftovers.length} credential-classified name(s) reached the `
        + `conductor environment (${classifiedLeftovers.sort().join(", ")}) — refusing to launch (§2.2)`);
    }
    // THE governed spawn. nodeId is the identity Python issued — the shell cannot mint one, and
    // SessionManager refuses a spawn without it (invariant 2).
    const session = manager.spawn({
      id: conductorPaneId,
      nodeId: identity.node_id,
      // `executable` is the binary the PRESENCE GATE resolved; argv[0] is its display name.
      spec: { file: launch.executable, args: argv.slice(1), cwd: launch.cwd, env, title: "CONDUCTOR" },
    });
    conductorLaunch = {
      ...conductorLaunch,
      pid: session.pid,
      sessionGeneration: session.generation,
      nodeId: identity.node_id,
      mcpState: "configured",
      leaseId: lease.lease_id || null,
      subscriptionRef: lease.subscription_ref || null,
      supervised: true,
    };
    panes.attachSession(conductorPaneId, conductorPaneId);
    conductorLaunch = {
      ...conductorLaunch,
      state: "running",
      nodeId: identity.node_id,
      mcpState: "configured",
      leaseId: lease.lease_id || null,
      subscriptionRef: lease.subscription_ref || null,
      pid: session.pid,
      sessionGeneration: session.generation,
      argv, executable: launch.executable, cwd: launch.cwd, supervised: true,
      authorityBoundary: runtimeBoundary,
      // the TICKET's boundary, kept alongside the runtime one: it carries the pinned hook command
      // this session's vendor process was configured with (U164 dispatches through that exact string)
      ticketAuthorityBoundary: ticket.authority_boundary || null,
      // the ticket's own account of where its slug came from (authoritative over the shell's read)
      modelProbe: ticket.model_probe || conductorLaunch.modelProbe || null,
      scrubbedCount: Array.isArray(launch.env_scrub_names) ? launch.env_scrub_names.length : null,
      // names only (§2.2) — kept so an in-runtime check can verify the child's env really lost them
      envScrubNames: Array.isArray(launch.env_scrub_names) ? launch.env_scrub_names.slice() : [],
      reason: null,
    };
    clearConductorInputResidue("a new conductor session was launched"); // fresh process, fresh input box
    persistLayoutSnapshot();
    pushConductor();
    pushState();
    emitLayoutNow();
    // W-35: `emit_conductor_launch.py:185` appends `--settings <profile.settings_json>`, so
    // `argv.join(" ")` reproduced the authority-boundary profile — hook command paths included —
    // into the durable log AND, through `rendererSink`, into the renderer console, which is the
    // least-trusted surface in the application. Identified by digest instead: which profile ran is
    // still answerable, and two launches are still distinguishable.
    log(`conductor: LIVE session running in pane 1 — ${redactArgvForLog(argv)} (pid ${conductorLaunch.pid}, `
      + `cwd ${launch.cwd}, ${conductorLaunch.scrubbedCount} credential var(s) scrubbed, `
      + `durable terminal ${lease.lease_id} ${lease.in_use}/${lease.allowance})`);

    // SW-CONDUCTOR-001 Phase 3: attach the pane's MCP harness BEFORE readiness runs — the
    // bridge's identity call is the first arrival that flips connectionState `configured` →
    // `connected` (readiness gate 1), and its preamble must be in the pane before readiness
    // gate 2 asks the model to call get_worker_status. Fail-closed: a refused attach only
    // logs; readiness then stalls on its own honest reason.
    await attachConductorBridge(identity.node_id, controlMint.token);

    const readiness = await runConductorReadiness();
    return { launched: true, sessionId, leaseId: conductorLaunch.leaseId, pid: conductorLaunch.pid,
      argv, ready: readiness.ready, readiness };
  } catch (e) {
    detachConductorBridge("the governed conductor launch failed");
    if (sovereignControl && identity.node_id) sovereignControl.revokeNode(identity.node_id);
    // Supervision denial may occur after ConPTY birth, while construction failure may be pre-birth.
    // Retain the terminal for an identified terminating process; release immediately only when no
    // process identity was registered.
    const why = `${e.name || "Error"}: ${e.message}`;
    const born = (e && e.sessionIdentity)
      || (Number.isInteger(conductorLaunch.pid) && Number.isInteger(conductorLaunch.sessionGeneration)
        ? { pid: conductorLaunch.pid, generation: conductorLaunch.sessionGeneration } : null);
    if (born) {
      conductorLaunch = {
        ...conductorLaunch,
        state: "terminating",
        pid: born.pid,
        sessionGeneration: born.generation,
        leaseId: lease.lease_id || conductorLaunch.leaseId || null,
        subscriptionRef: lease.subscription_ref || conductorLaunch.subscriptionRef || null,
        reason: `${why}; process termination requested — lease retained until matching PTY exit`,
      };
      if (!(e && e.processExitPending)) {
        try { manager.kill(conductorPaneId); } catch { /* already terminal */ }
      }
      const current = manager.processIdentity(conductorPaneId);
      if (current && current.pid === born.pid && current.generation === born.generation) {
        pushConductor();
        return { launched: false, reason: why, awaitingProcessExit: true };
      }
      if (["release_pending", "release_failed", "exited"].includes(conductorLaunch.state)) {
        pushConductor();
        return { launched: false, reason: why, processExited: true };
      }
    }
    const rel = await releaseConductorTerminalWithRetry(sessionId, "spawn failed", "failed", why);
    const releaseFailed = !rel || rel.ok !== true;
    conductorLaunch = {
      ...conductorLaunch,
      state: releaseFailed ? "release_failed" : "failed",
      reason: releaseFailed
        ? `${why}; durable terminal release failed (${(rel && rel.error) || "unknown"})`
        : why,
      endedAt: new Date().toISOString(),
    };
    log(`conductor: governed spawn FAILED (${releaseFailed
      ? "terminal release failed; retry scheduled" : "terminal handed back"}, pane 1 stays un-launched): ${why}`);
    pushConductor();
    return { launched: false, reason: why };
  }
}

/** The session ended (exit or kill) — release the durable terminal and report honestly. */
function onConductorSessionEnded(event) {
  const transition = advanceConductorSessionLifecycle(
    conductorLaunch, event, conductorPaneId, new Date().toISOString(),
  );
  if (transition.action === "ignore") return null;
  const sessionId = conductorLaunch.sessionId;
  const nodeId = conductorLaunch.nodeId;
  conductorLaunch = transition.launch;
  // SW-CONDUCTOR-001 Phase 3: the pane session the bridge was attached to is ending — this
  // point is only reached for the REAL conductor session (non-matching events returned
  // "ignore" above). Stop the relay now; the credential is revoked just below, and a bridge
  // must not outlive either.
  detachConductorBridge("the conductor session ended");
  if (transition.action === "await_process_exit") {
    pushConductor();
    return null;
  }
  // The input box died with the session; there is no residue to splice onto any more.
  clearConductorInputResidue("the conductor session ended");
  if (sovereignControl && nodeId) sovereignControl.revokeNode(nodeId);
  conductorLaunch = { ...conductorLaunch, mcpState: "disconnected" };
  if (transition.releaseAuthority) {
    conductorVoiceAuthority.reset("the supervised conductor process exited", {
      source: "node_pty_exit",
      process_exited: true,
      pane_id: event.id,
      session_id: sessionId,
      generation: event.generation,
      pid: event.pid,
    });
    // U181: the process that could rewrite the policy files is gone, and the next launch takes its
    // own baseline. Holding this one would verify a dead session's bytes against a live launch.
    conductorPolicyBytes.clear();
  }
  if (transition.releaseLease) {
    const release = reconcileConductorTerminalRelease(sessionId, "conductor process exit").catch((error) => {
      scheduleConductorReleaseRetry(sessionId);
      throw error;
    });
    pushConductor();
    return release;
  }
  pushConductor();
  return null;
}

// ---- operator command surface: approval-queue drawer (Phase 15E .objective; OP-7 §12.5 item 5) ---
// The unified drawer surfaces plan approvals / protected actions / clarifications with a badge count.
// The AUTHORITY + the queue are Python-side (control_plane/orchestration/operator_surface.ApprovalQueue):
// only the operator resolves an item (invariant 1); a gate-failed plan is not approvable (invariant 16).
// This module folds the drawer snapshot with the SAME pure core the JS tests cover
// (terminal/compositor/approval-drawer). Fail-closed: an unavailable feed renders empty, never a
// fabricated pending item or count.
//
// Phase 17D `.events` (finding F2): 16D sourced this drawer from a producer that built a canned plan
// and two canned commands on every fetch, so the operator's first launch showed three pending
// approvals no session had produced. The drawer is now folded from THIS run's own recorded approval
// events (approvals/session-events.js → emit_approval_drawer.py --events), re-derived by the real
// classifiers Python-side. An empty session shows an EMPTY drawer, and the demonstration trio is a
// test-only fixture (tests/support/demo_approval_queue.py) no product path can reach.
// …and isolated for a diagnostic run exactly as RECOVERY_DIR is (spec-audit F9): `begin()` TRUNCATES
// this file, so a self-check launched while the operator's shell is open would wipe the drawer log
// of a live session — and its own "the drawer was empty until this run caused something" leg would
// be satisfied by that truncation rather than by an absence.
const sessionApprovals = new SessionApprovalLog({
  log,
  logPath: process.env.SHELL_SELFCHECK
    ? path.join(sowStateRoot(), ".approvals", "selfcheck", "session-events.jsonl")  // F-131
    // F-131. The normal path defaulted to apps/desktop/.approvals (the install tree); pin it to
    // the state root so operator transcripts are not written into, or lost with, the install.
    : path.join(sowStateRoot(), ".approvals", "session-events.jsonl"),
});
let sessionApprovalsStarted = false;   // the log is truncated once per PROCESS, not per renderer load

async function fetchApprovalDrawerModel() {
  const res = await sourceApprovalDrawerFeed({ cwd: REPO_ROOT, eventsPath: sessionApprovals.path() });
  const snapshot = res.ok ? res.feed.drawer : null; // null ⇒ buildApprovalDrawer yields honest empty
  const view = buildApprovalDrawer(snapshot);
  const model = {
    ...view,
    summary: summarizeApprovalDrawer(view),
    source: res.ok ? "session_events" : "fail_closed",
    sourced: res.ok === true,
    // what the drawer was folded FROM, so an empty drawer is legible as "nothing happened yet"
    // rather than "the feed broke" — two very different things to show the operator.
    eventCount: res.ok ? (res.feed.event_count || 0) : 0,
    decisionCount: res.ok ? (res.feed.decision_count || 0) : 0,
    demoItems: false,
    sideEffectsOwed: res.ok ? (res.feed.side_effects_owed || null) : null,
  };
  if (!res.ok) model.error = res.error;
  return model;
}

// Cache the last sourced model so the launch badge push does not block on the emitter; refreshed on
// startup and on every fetch.
let lastApprovalModel = { ...buildApprovalDrawer(null), summary: summarizeApprovalDrawer(buildApprovalDrawer(null)), source: "fail_closed", sourced: false, error: "not yet sourced" };

async function refreshApprovalModel() {
  lastApprovalModel = await fetchApprovalDrawerModel();
  return lastApprovalModel;
}

function pushApprovals() {
  if (!win || win.isDestroyed()) return;
  win.webContents.send("shell:approvals", lastApprovalModel);
}

// ---- conductor voice-IN affordance (Phase 15E .voice; OP-8 §13.5) -------------
// The conductor pane gains a push-to-talk mic: the operator SPEAKS to the conductor and the
// transcript enters its input on the same path as typing. The ROUTING authority is Python-side
// (voice_bridge/conductor_voice.ConductorVoiceBridge over the real CommandBroker): ordinary chat
// flows directly to the conductor input, a protected/destructive action proposes→approves (never
// executes — invariant 25) and surfaces in the approval drawer, a low-confidence transcript
// clarifies. This shell draws the mic affordance + the last-utterance badge with the SAME pure core
// the JS tests cover (terminal/compositor/voice-indicator). There is NO speaker/TTS affordance
// (I-V2/D-VOICE-02: STT-only; voice-OUT is OWED-BY-OPERATOR-DECISION per OP-8 §13.6, never faked).
// Phase 16E `.wire` (closes the WRITE half of U67): the talk button now SOURCES the engine-selected
// conductor_voice_feed@1.0 (voice-source → emit_conductor_voice → the REAL ConductorVoiceBridge) and,
// on a CHAT outcome, DELIVERS the transcript into the conductor input — the same command path as
// typing (OP-8 §13.5). The VISIBLE mock-engine indicator rides on the feed's engine descriptor (never
// a silent pretend-to-hear). The interactive conductor ConPTY drive itself is operator-run (directive
// §6): with no admitted live conductor session, a routed CHAT is honestly OWED to 16F, never faked.
// Phase 17C `.probe` (U74 / OP-11 finding F1): the STT-engine state is its own ASYNCHRONOUS fact, owned
// by `voiceProbe`, not a side effect of a capture. The operator saw "mock engine" on a host with WSL
// Parakeet installed because the probe budget (8 s) was below the measured NeMo ASR import cost (7–18 s
// here) and one cold miss was then cached for the app's life. The budget is now 90 s — which is only
// safe because the probe runs OFF this path: `voiceState()` reads `voiceProbe.state()`, which is
// synchronous and instant and answers `probing` while the question is open. An open question renders as
// one; it is never answered "mock" by default.
let voiceProbe = null;
//: A forced re-probe spawns a real WSL NeMo import; the renderer may ask for one, but not in a loop.
const FORCED_PROBE_MIN_INTERVAL_MS = 5000;
let lastForcedProbeAt = null;

function ensureVoiceProbe() {
  if (!voiceProbe) {
    voiceProbe = new VoiceProbe({ cwd: REPO_ROOT, log });
    // When a re-probe started by a stale read settles, push the corrected state. Without this the
    // chrome would hold a stale answer until the next unrelated repaint.
    voiceProbe.onSettle((s) => { log(`voice: STT engine re-probe → ${s.state} (${s.elapsedMs}ms)`); pushVoice(); });
  }
  return voiceProbe;
}

let lastVoiceFeed = null; // the last sourced conductor_voice_feed@1.0 (engine + outcome) — drives the badge
// …and what the WRITE that carried it actually did. Phase 17C `.close`: the badge used to be built from
// the routing verdict alone, so "Delivered to conductor" appeared for a CHAT the live session never
// received. The operator reads that badge; it now reads this too.
let lastVoiceWrite = null;

// ---- Phase 17C `.mic`: real microphone PCM ------------------------------------
// The renderer captures the operator's speech with `getUserMedia`, encodes it to 16 kHz mono 16-bit WAV
// (apps/desktop/voice/wav.js) and sends the BYTES here. WSL Parakeet transcribes a FILE, so the bytes
// land on disk for the few seconds of the round trip — under the repo (§2.5), git-ignored, and deleted
// in a `finally` by `CaptureStore.withCapture` whether the transcription succeeds, fails, or throws
// (invariant 26, transcribe-then-discard: an invariant that depends on the happy path is not one).
let captureStore = null;
let stopCaptureJanitor = null;
function ensureCaptureStore() {
  if (!captureStore) {
    captureStore = new CaptureStore({ appDir: sowStateRoot() });  // F-131
    // A kill mid-transcription outruns any `finally`, so recorded speech can survive a crash. Purging
    // at startup, periodically, and at teardown bounds a fresh cross-instance orphan to the
    // ten-minute safety age plus one janitor minute while the replacement shell remains open.
    // This must be called at BOOTSTRAP, not
    // lazily on the first capture: constructed on first use, the "startup purge" only ran when the
    // operator next used voice, so an orphan from a crash could sit through weeks of sessions in which
    // they never pressed talk. The comment claimed one session; the code delivered no such bound.
    const purged = captureStore.purge();
    if (purged.removed || purged.skipped) {
      log(`voice: purged ${purged.removed} orphaned capture file(s)`
        + `${purged.skipped ? `, left ${purged.skipped} recent (possibly another instance's live capture)` : ""}`);
    }
    stopCaptureJanitor = captureStore.startJanitor();
  }
  return captureStore;
}

// How many captures are in flight. `voiceState().control.capturing` was hard-coded false (**U133**), so
// while the operator waited out a real WSL transcription — seconds to minutes — nothing in the chrome
// changed and the natural reading was "it is hung; press again". This makes the wait visible.
let capturesInFlight = 0;
//: A HARD cap, not a badge counter. Each real capture writes megabytes and spawns py → wsl → a 0.6b ASR
//: model load; the sibling `voice:probe` handler is rate-limited for strictly less than this, and the
//: only thing serialising captures otherwise is a flag in the renderer — the surface invariant 29 says
//: never to trust. One at a time also matches the physical truth: there is one operator and one mic.
const MAX_CONCURRENT_CAPTURES = 1;

// The engine descriptor the chrome draws, from TWO facts that answer DIFFERENT questions:
//   * the PROBE answers "is a real engine reachable right now" — a maintained fact, re-taken on expiry;
//   * the last CAPTURE answers "what transcribed the last utterance" — historical, per-utterance.
// Availability therefore always comes from the probe (the fact that is kept current); the capture only
// supplies the engine identity, and only when a real engine genuinely did the transcribing.
//
// The rule this replaces let ANY capture reporting `real_available:true` win permanently, justified by
// a claim that a capture proves more because "a real transcription actually happened". That was false:
// the default capture path routes the stand-in mock and takes its `real_available` from the same probe
// mechanism — so the rule pinned one moment's answer for the life of the process. That is precisely the
// `lru_cache(maxsize=1)` defect this unit exists to remove, re-implemented one layer up: an operator
// whose WSL later went away would keep being told "parakeet-wsl ready" until they restarted the shell.
function voiceEngineDescriptor() {
  const probe = ensureVoiceProbe().ensureFresh();  // a stale answer re-arms a real probe as a side effect
  const captured = lastVoiceFeed && lastVoiceFeed.engine;
  if (!captured) return probe.engine;
  // The one case where the capture's own identity is what to show: a REAL engine actually transcribed —
  // and even then only while the probe still agrees it is reachable (never assert a capability that has
  // since gone away, invariant 3).
  if (captured.mock === false && captured.real_available === true && probe.state === "available") return captured;
  return probe.engine;
}

// Push the voice state to the renderer. The probe settles ASYNCHRONOUSLY (7–18 s after launch on this
// host), so the badge must flip itself when the answer lands — an operator who never clicks anything
// must still stop seeing "probing…" once the question is answered.
function pushVoice() {
  if (!win || win.isDestroyed()) return;
  win.webContents.send("shell:voice", voiceState());
}

function voiceState() {
  const probe = ensureVoiceProbe().ensureFresh();
  const control = voiceControl({
    available: Boolean(conductorPaneId),
    // U133: true while a capture is genuinely in flight — the render model already had `capturing` /
    // `listening`; only main's hard-coded `false` kept it dark.
    capturing: capturesInFlight > 0,
    engine: voiceEngineDescriptor(), // fail-closed to a VISIBLE mock/probing indicator, never a claim
  });
  const badge = lastVoiceFeed ? voiceOutcomeBadge(lastVoiceFeed.outcome, lastVoiceWrite) : null;
  return {
    control,
    badge,
    summary: summarizeVoice(control, badge),
    speechOut: false,
    engine: control.engine,
    // Phase 17C `.disarm` (U166 / invariant 27): whether a voice turn is restricting the conductor
    // session right now — the state that used to be invisible AND permanent. It carries its own
    // recovery text, so the chrome cannot describe an exit this service does not implement.
    turn: conductorVoiceAuthority.turnState(),
    // …folded by the same pure render model the JS tests cover, so the sandboxed renderer draws it
    // rather than deciding what it means (invariant 1; the renderer has no require()).
    turnIndicator: voiceTurnIndicator(conductorVoiceAuthority.turnState()),
    // the raw probe record, so the Inspector/receipt can see the measured elapsed time and the reason
    // rather than only the label — a badge that says "probing…" should be checkable against a clock.
    probe: { state: probe.state, reason: probe.reason, elapsed_ms: probe.elapsedMs,
             probes: probe.probeCount, stale: probe.stale === true, reprobing: probe.reprobing === true },
  };
}

// Write a CHAT transcript into the conductor pane's input — the SAME ConPTY path pane:input/typing uses.
// Fail-closed and honest: only a RUNNING governed conductor session may receive bytes (invariant 2).
// It self-authorizes nothing (invariant 1): the CHAT vs propose vs clarify decision was made Python-side;
// the shell only forwards a CHAT verdict after the pane-state and exact-echo guards below.
//
// Phase 17C `.close`: the BODY and the SUBMIT key are two separate writes, and the submit key is sent
// ONLY after this shell has SEEN the pane echo that body back. Three defects made that necessary, and
// the first two were found by the mandatory reviews of the first draft of this unit:
//
//  1. A single `body\r` chunk does not reach the live conductor as a submitted message. MEASURED here
//     (falsification F2): the transcript echoed into pane 1, the CLI showed activity, and the model
//     never answered the question within 180 s — while the code reported `{written:true}` and the
//     operator's badge said "Delivered to conductor". A paste is not a keystroke sequence.
//  2. An UNCONDITIONAL submit key answers whatever pane 1 is currently showing. The live `claude`
//     session gates its own tool use with in-pane prompts ("Do you want to proceed? ❯1. Yes  2. Yes,
//     and don't ask again  3. No"), so a bare `\r` arriving while one is open CONFIRMS ITS DEFAULT —
//     a protected action executed from an ordinary spoken sentence, with no CommandBroker, no approval
//     queue, no drawer. That is precisely the authority expansion invariant 25 exists to forbid, and
//     voice must never be able to do it. A permission prompt does not echo the body, so requiring the
//     echo refuses to submit into one, by construction rather than by hoping.
//  3. A blind timer cannot tell either case from success. The echo wait is an OBSERVATION, which is
//     also what 17A `.roundtrip` does on the typed path — the only shape this repo has ever proven.
//
// The echo is read from the session's own ring buffer (the bytes the ConPTY emitted, invariant 27),
// compared on ALPHANUMERICS ONLY: the TUI re-renders its input box with escape sequences and box
// borders, and may wrap a long utterance across lines, so anything stricter would fail on a working
// path. Failure to observe it withholds the submit and says so — the operator sees "not submitted",
// never a fabricated delivery.
// The matching rule itself lives in voice/echo-confirm.js with its own tests, because it had to be
// corrected once already: a plain substring test over the repaint stream FAILED on a run whose pane
// demonstrably rendered the utterance in full (a ConPTY repaint of a full-screen TUI splits the line).
//
// `.close-revalidate` — BOTH mandatory reviews found the same two BLOCKING defects in the above, and
// both are fixed here rather than argued with:
//
//  A. THE WINDOW WAS NOT BOUNDED. The echo search started at `snapshot().length`, an index into a ring
//     buffer whose ORIGIN MOVES. One front-chunk eviction (routine under a repainting TUI) made the
//     offset outrun the snapshot, and the code then searched the WHOLE SCROLLBACK — so an EARLIER echo
//     of the same sentence (the operator naturally repeats an utterance that looked unanswered) could
//     satisfy the gate and fire `\r` into whatever was on screen. The old comment called the wider
//     window benign because it "can only make the confirmation easier to satisfy": being hard to
//     satisfy IS this gate's safety function. It now reads the appended region or NOTHING
//     (`RingBuffer.sliceFrom` → null), and null withholds the submit.
//     The old comment also claimed an "occurrence COUNT … so a repeated utterance still needs a new
//     echo of its own". There was no such count — `echoedInOrder` is an in-order containment scan —
//     and the byte offset was the only thing carrying that property. The claim is deleted; the offset
//     is now sound enough to actually carry it.
//  B. ONLY THE SUBMIT KEY WAS GATED. The BODY — the operator's own sentence — was typed into whatever
//     the pane was showing, and the live CLI's permission prompt is a NUMBERED selection list whose
//     affordance is digits. "What is 31 plus 32? …" carries 3, 1, 3, 2. Nothing is written now unless
//     `paneAcceptsTypedText` finds positive evidence the pane is showing its text input
//     (voice/pane-state.js — fail closed: an unknown state refuses).
// The decision itself lives in `voice/conductor-write.js` over injected I/O, with unit tests that go
// red when any guard is removed. It used to live here, and both reviews said the same thing about
// that: main.js cannot be required headlessly, so half of `.close`'s BLOCKING-1 fix could be reverted
// with all 393 + 186 tests still green. Main's job is now the binding and nothing else.
// W-39 removed `operatorInputResolvesResidue` from this import: its only caller was the `pane:input`
// handler, and that call is gone. The predicate itself is untouched and still exported and tested —
// it was never the defect. A dead import here would be a standing invitation to call it again from
// the channel this unit just removed it from.
const { deliverChat } = require("./voice/conductor-write");

/** This session's MONOTONIC stream position (every byte its ConPTY has ever emitted). */
function paneStreamPosition(paneId) {
  try {
    return manager.registry.get(paneId).buffer.totalWritten;
  } catch {
    return null;         // no session / no buffer — the caller fails closed on a null position
  }
}

/**
 * What this session's ConPTY emitted after stream position `from`, or NULL when that window can no
 * longer be answered exactly (trimmed away, or no buffer). Null is not "nothing was echoed" — it is
 * "this shell cannot see", and the caller must treat the two differently.
 */
function paneEmittedSince(paneId, from) {
  try {
    const slice = manager.registry.get(paneId).buffer.sliceFrom(from);
    return slice === null ? null : slice.toString("utf8");
  } catch {
    return null;
  }
}

/** Everything this session's ConPTY has emitted (for the pane-state precondition). */
function paneEmittedAll(paneId) {
  try {
    return manager.registry.get(paneId).buffer.snapshot();
  } catch {
    return null;
  }
}

// A body written but never submitted stays in the conductor's input box. The next utterance would be
// APPENDED to it and the pair submitted as one prompt — two spoken sentences becoming one message the
// operator never said, badged "Delivered to conductor". So a withheld submit RECORDS the residue and
// the next delivery refuses until the operator submits or cancels it with Enter or Ctrl-C.
let conductorInputResidue = null;
function clearConductorInputResidue(why) {
  if (!conductorInputResidue) return;
  log(`voice: conductor input residue cleared (${why})`);
  conductorInputResidue = null;
}

/**
 * Write a routed CHAT transcript into the LIVE conductor pane's input.
 *
 * The target is ALWAYS the current conductor pane — deliberately not a parameter. It used to be one
 * (defaulting to the conductor), and the `.mic` receipt shows what that permitted: the operator's
 * transcript was Enter-submitted into a `powershell.exe` stand-in pane, i.e. voice text reaching a
 * command interpreter, which is the shape invariant 25 exists to forbid. A diagnostic caller now gets
 * the same refusal a stray caller would.
 */
async function deliverConductorChat(text) {
  const paneId = conductorPaneId;
  try {
    return await deliverChat(text, {
      paneId,
      hasSession: () => Boolean(manager && manager.registry && manager.registry.has(paneId)),
      isTerminal: () => manager.registry.isTerminal(paneId),
      launchState: () => conductorLaunch.state,
      // Minted and hash-pinned by the Node Runtime launch ticket; vendor/model chrome is only the
      // secondary interaction-state guard and never supplies authority. The ticket cannot assert
      // runtime enforcement; launchConductorSession upgrades this only after main's service listens.
      authorityBoundary: () => conductorLaunch.authorityBoundary,
      armAuthority: async (body) => {
        try { return { ok: true, ...conductorVoiceAuthority.arm(body) }; }
        catch (e) { return { ok: false, reason: `${e.name || "Error"}: ${e.message}` }; }
      },
      cancelAuthority: (turnId, reason) => conductorVoiceAuthority.cancel(turnId, reason),
      // Phase 17C `.disarm`: what the supervisor still holds for THIS turn after the submit key —
      // "admitted" (the CLI presented the payload back), "pending" (not yet), or "ended" (the
      // operator's keystroke or a cancel took it). Without this the badge would say "Delivered to
      // conductor" for an utterance the operator's own next keypress had just voided.
      // U182: the fate is answered by the authority's own per-turn state machine, not by scanning
      // (and deep-copying) an audit the least-trusted party can flood every 120 ms. It still keeps
      // the property spec-audit M-D asked for — a turn admitted and then ended by the operator's next
      // keystroke, a race of one poll interval, DID reach the model and stays a delivery — and the
      // one M-C asked for: WHY it ended, because "ended" collapsed four causes while the operator was
      // told one of them. U180: the name says which fact measured it.
      turnFate: (turnId) => conductorVoiceAuthority.fateOf(turnId),
      emittedAll: () => paneEmittedAll(paneId),
      streamPosition: () => paneStreamPosition(paneId),
      emittedSince: (from) => paneEmittedSince(paneId, from),
      write: (data) => manager.write(paneId, data),
      getResidue: () => conductorInputResidue,
      setResidue: (r) => {
        conductorInputResidue = { ...r, at: new Date().toISOString() };
        log(`voice: the utterance was NOT submitted (${r.why}) — it is sitting in pane ${paneId}'s input; `
          + "the next spoken utterance is refused until you clear it");
      },
      now: () => Date.now(),
      sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
    });
  } catch (e) {
    return { written: false, submitted: false, reason: `${e.name || "Error"}: ${e.message}` };
  }
}
// ---- G25: persistent operator typing surface --------------------------------
// The renderer input feeds THE SAME guarded delivery voice uses (deliverConductorChat:
// governed-conductor-only, residue guard, accepts-text, echo-confirmed submit). Turns are
// kept in a capped in-memory transcript and pushed to the renderer; nothing is written to
// disk here. A sweep probe (payload.__sweep) short-circuits WITHOUT delivery so the U177
// channel-closure check can drive this channel without spending a Conductor turn.
const conductorTranscript = [];
function pushTranscriptTurn(turn) {
  conductorTranscript.push(turn);
  if (conductorTranscript.length > 200) {
    conductorTranscript.splice(0, conductorTranscript.length - 200);
  }
  try {
    const w = Array.from(require("electron").BrowserWindow.getAllWindows())[0];
    if (w && !w.isDestroyed()) {
      w.webContents.send("shell:conductor-transcript", conductorTranscript.slice(-50));
    }
  } catch (_e) { /* no window yet - transcript stays in main */ }
}
// G26 evidence driver — a DEV/EVIDENCE loopback bridge, NOT a product surface. Its logic lives in
// control/operator-text-driver.js so it is testable without the Electron main process; the
// effectful operations are injected here. Per F-128 it is removed from the product launch env
// (shell/modules/sow.json no longer sets the port) and, when a developer does enable it, it fails
// closed without a per-launch bearer token and refuses browser-Origin / non-loopback-Host /
// non-JSON / oversized requests, and survives a bind conflict instead of crashing the shell.
const { startOperatorTextDriver } = require("./control/operator-text-driver");
startOperatorTextDriver({
  log,
  handlers: {
    send: (payload) => handleOperatorText(payload),
    launchConductor: () => launchConductorSession({ reason: "G26 governed round-trip" }),
    interrupt: () => ({ interrupted: Boolean(paneWriter.interrupt(conductorPaneId)) }),
    state: () => ({
      launchState: conductorLaunch.state,
      alive: (() => { try { return manager.registry.has(conductorPaneId)
        && !manager.registry.isTerminal(conductorPaneId); } catch { return false; } })(),
      transcript: conductorTranscript.slice(-20),
      emittedTail: (function () { try { const a = paneEmittedAll(conductorPaneId); return a ? a.slice(-700) : null; } catch { return null; } })(),
      paneStreamPositionNow: paneStreamPosition(conductorPaneId),
    }),
  },
});
ipcMain.handle("conductor:operator-text", (_e, payload) => handleOperatorText(payload));

// Journal attribution reads the same model chrome as the conversational surface; no launch or gate.
configureJournalModelSource((paneId) => (paneChrome.get(paneId) || {}).model_slug || null);
const answerTally = createAnswerTally();
function paneAnswerCount(paneId) {
  try { return answerTally.count(runtimeJournal(), paneId); }
  catch { return null; } // unknown is not a fabricated zero
}


async function deliverConductorConversation(text) {
  return retrieveAndDeliver({ message: text,
      journalSource: runtimeJournal,
      budgetSource: () => createStore().budget(),
      write: (body) => deliverConductorChat(body),
      window: readinessWindow,
      panes: Array.from(panes.panes.keys()).filter(id => id !== conductorPaneId).map(id => ({
        pane_id: id, node_id: (liveWorkerRecords().find(r => r.paneId === id) || {}).nodeId
          || "(not registered)", model: (paneChrome.get(id) || {}).model_slug || "(not reported)",
        live: liveWorkerRecords().some(r => r.paneId === id),
        answer_count: paneAnswerCount(id),
      })), log,
    });
}

function recordConversationContext(outTurn, res) {
    if (res.context && res.context.notice) {
      outTurn.workspace_view = { state: res.context.state, notice: res.context.notice,
        entry_ids: res.context.entry_ids, pane_ids: res.context.pane_ids,
        truncated: res.context.truncated, roster_attached: res.context.roster_attached,
        source: "observed_pane_output", self_published: false };
      pushTranscriptTurn({ utc: new Date().toISOString(), dir: "sys", text: res.context.notice });
    }
}

async function handleOperatorText(payload) {
  const p = payload && typeof payload === "object" ? payload : {};
  const text = String(p.text || "").trim();
  if (p.__sweep) return { ok: true, swept: true, delivered: false };
  if (!text) throw new Error("empty-directive");
  if (text.length > 4000) throw new Error("directive-too-long");
  // WHOSE conductor is answering, read from the descriptor the shell actually resolved rather than
  // from a literal (LOCAL-01 F-3). These two fields were hardcoded to `openai_codex_cli` /
  // `gpt-5.6-sol`, so every transcript turn claimed a frontier provider no matter what was really
  // backing the pane — and under OD-31 that provider cannot even be authorized. A transcript that
  // names the wrong model is the drift U65 closed for the badge, reappearing one surface over.
  const cdesc = conductorDescriptor() || {};
  const turnProvider = cdesc.provider_id || null;
  const turnModel = cdesc.model_id || null;
  const outTurn = { utc: new Date().toISOString(), dir: "out", text,
                    provider: turnProvider, model: turnModel,
                    delivered: false, submitted: false, reason: "",
                    workspace_view: { state: "not_attached", source: "observed_pane_output",
                      self_published: false,
                      notice: "No worker view attached yet. Use /workspace to request the full recent view." } };
  pushTranscriptTurn(outTurn);

  // OPTION C, the operator's ruling (ENTRY 017 / OD-32): the Conductor launches, accepts typing,
  // and SPAWNS NOTHING until a model is selected and a message is sent. This is that deferred
  // spawn, and it is the quota protection that replaces H-10 — the session is born here, on the
  // operator's first message, rather than at startup. `launchConductorSession` is itself
  // fail-closed and refuses when a session is already running, so this cannot double-spawn.
  const conductorAlive = conductorLaunch.state === "running"
    && manager && manager.registry.has(conductorPaneId);
  if (!conductorAlive) {
    log(`conductor: no live session — launching on the operator's first message (option C)`);
    const born = await launchConductorSession({ reason: "operator sent a message (option C deferred spawn)" });
    if (!born || born.launched !== true) {
      outTurn.reason = `the conductor session could not be started: ${(born && born.reason) || "fail-closed"}`;
      outTurn.error = "CONDUCTOR_COMMUNICATION_FAILED";
      pushTranscriptTurn({ utc: new Date().toISOString(), dir: "sys", text: outTurn.reason });
      return { ok: false, turn: outTurn };
    }
  }
  const fromPos = paneStreamPosition(conductorPaneId);
  let res;
  try {
    res = await deliverConductorConversation(text);
    recordConversationContext(outTurn, res);
  } catch (e) {
    res = { written: false, submitted: false, reason: (e && e.message) || String(e) };
  }
  outTurn.delivered = Boolean(res.written);
  outTurn.submitted = Boolean(res.submitted);
  outTurn.reason = String(res.reason || "");
  if (!outTurn.submitted) {
    // G17 vocabulary: silence is not an outcome - surface it on the card/transcript.
    outTurn.error = "CONDUCTOR_COMMUNICATION_FAILED";
    pushTranscriptTurn({ utc: new Date().toISOString(), dir: "sys", text: outTurn.reason });
    return { ok: false, turn: outTurn };
  }
  // Response capture: snapshot what the ConPTY appended after the submit was admitted,
  // bounded quiet-window so a long generation still lands in THIS transcript turn.
  let deadline = Date.now() + 6000;
  let last = "";
  await new Promise((r) => setTimeout(r, 800));
  while (Date.now() < deadline) {
    // F-129. paneEmittedSince(paneId, from) -- the paneId was omitted, so `from` was undefined,
    // registry.get(<number>) threw, and every "in" transcript turn captured "" (responseChars 0)
    // while the loop always burned the full quiet window. Pass the conductor pane explicitly.
    const chunk = fromPos === null ? null : paneEmittedSince(conductorPaneId, fromPos);
    if (typeof chunk === "string" && chunk.length > last.length) {
      last = chunk;
      deadline = Math.min(deadline + 700, Date.now() + 6000);
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  const inTurn = { utc: new Date().toISOString(), dir: "in",
                   text: last.slice(-4000), provider: turnProvider,
                   model: turnModel };
  pushTranscriptTurn(inTurn);
  return { ok: true, turn: outTurn, responseChars: inTurn.text.length };
}


// ---- renderer IPC (intents only; the renderer never touches a PTY directly) --
async function selectConductorFromPicker(selection) {
  if (conductorLaunch.state === "running" || conductorLaunch.state === "launching") {
    return { selected: false, error: "conductor replacement requires governed succession; stop the current session first" };
  }
  if (!selection || selection.targetPaneId !== conductorPaneId || selection.role !== "conductor") {
    return { selected: false, error: "selection is not a pre-launch conductor-pane intent" };
  }
  const supplied = selection.option || {};
  const options = (lastPickerModel && lastPickerModel.picker && lastPickerModel.picker.options) || [];
  const option = options.find((o) => o && o.adapter === supplied.adapter
    && o.model_slug === supplied.model_slug && o.label === supplied.label);
  if (!option || option.available !== true || option.registered !== true
      || option.conductor_capable !== true || !Array.isArray(option.roles)
      || !option.roles.includes("conductor")) {
    return { selected: false, error: "model is not an available registered conductor-capable picker option" };
  }
  const persisted = await selectConductorPreference({
    provider_id: option.provider, adapter_id: option.adapter, model_id: option.model_slug,
    display_name: option.label, permission_profile_id: "pp-conductor-pane", workspace: REPO_ROOT,
  }, { cwd: REPO_ROOT });
  if (!persisted || persisted.ok !== true) {
    return { selected: false, error: (persisted && persisted.error) || "selection validation failed" };
  }
  conductorModelProbe = null;
  await sourceConductorFeed();
  await sourceConductorSpawn();
  pushConductor();
  log(`conductor: operator selected ${option.provider}/${option.model_slug} before launch`);
  return { selected: true, descriptor: persisted.descriptor, state: conductorState() };
}

function registerIpc() {
  // The renderer is the least-trusted surface (invariant 29 — never trust the harness). It may ask
  // for a pane; it may NOT choose the child's environment or working directory. Those two now carry
  // governance (the credential scrub and the workspace binding), so they are accepted ONLY from a
  // main-process governed launch and are stripped here.
  // W-29: the scrubbed env is supplied HERE, at the boundary, and after the sanitised spec so no
  // renderer key can overwrite it. Not inside `ptyFactory`'s `spec.env || { ...process.env }`
  // fallback, deliberately: `lastPtySpawn.inheritedEnv` is `!spec.env`, and `childEnvIsScrubbed`
  // reads `inheritedEnv === true` to mean "the §2.2 scrub was not applied at all". Scrubbing inside
  // the fallback would leave that flag either lying in a receipt or true for nobody — a guard that
  // can never fire, which is the U367 class the U446 debt is already about. Supplying an env means
  // one genuinely IS supplied, so the flag keeps its meaning and the guard stays live for the paths
  // that still supply none.
  // G20/S-11: a NEW session container holds NO process. It is EMPTY with backend none,
  // model reference null and pid null until the operator selects an execution type;
  // only an explicit, ticketed selection ever reaches ptyFactory afterwards.
  const emptyPanes = new Map(); // G21: id -> {state, backend, modelRef, pid}
  function createEmptyPane(spec = {}) {
    const id = `pane-${++paneSeq}`;
    emptyPanes.set(id, { state: "EMPTY", backend: "none", modelRef: null, pid: null });
    panes.createPane({
      id,
      sessionId: null,
      title: spec.title || "EMPTY - select execution type",
      backend: "none",
      modelRef: null,
      pid: null,
      state: "EMPTY",
    });
    persistLayoutSnapshot();
    pushState();
    emitLayoutNow();
    return id;
  }
  ipcMain.handle("pane:create-empty", (_e, spec) => createEmptyPane(
    sanitizeRendererSpec(spec || {})));

  // G21/S-11: execution-type selection happens while the container is EMPTY -
  // before any process exists, with no prior exit and nothing to refuse. A model
  // reference is required only for backends that take one; Initialize (spawning)
  // is a separate, later operator act that goes through the governed launchers.
  const EXECUTION_TYPES = Object.freeze(["local_model", "api_model", "opencode", "powershell"]);
  const MODEL_BACKENDS = Object.freeze(["local_model", "api_model"]);
  ipcMain.handle("pane:select-execution", (_e, payload) => {
    const p = payload && typeof payload === "object" ? payload : {};
    const id = String(p.id || "");
    const type = String(p.executionType || "");
    const meta = emptyPanes.get(id);
    if (!meta) throw new Error("unknown-or-not-empty: " + id);
    if (meta.state !== "EMPTY") {
      throw new Error("not-selectable-from-state-" + meta.state);
    }
    if (!EXECUTION_TYPES.includes(type)) {
      throw new Error("unknown-execution-type: " + type);
    }
    if (MODEL_BACKENDS.includes(type) && !p.modelRef) {
      throw new Error("model-ref-required-for-" + type);
    }
    meta.backend = type;
    meta.modelRef = p.modelRef || null;
    meta.state = "CONFIGURING";
    persistLayoutSnapshot();
    pushState();
    return JSON.parse(JSON.stringify(meta));
  });
    ipcMain.handle("pane:new", (_e, spec) => createPaneWithSession(
    { ...sanitizeRendererSpec(spec), env: scrubCredentialEnv(process.env) }));
  ipcMain.handle("pane:input", (_e, id, data) => {
    // NOTE (Phase 17C `.disarm`): bytes arriving here do NOT end a voice turn, and the first draft of
    // that sub-step had them doing so. They look like the operator typing — this is the channel their
    // keystrokes travel — but xterm.js also emits `onData` for the terminal REPLIES it generates by
    // itself when the pane's own process prints a cursor-position or device-attribute query. The
    // supervised CLI prints into this pane, so it could have elicited an "operator" byte on demand
    // and disarmed its own restriction: the forged-lifecycle bypass again, one channel over. Only
    // `before-input-event` — the OS input path, which the child is not on — is operator provenance.
    // W-39: the residue block is NOT cleared here, and the paragraph above is why. These bytes are
    // not operator provenance — xterm.js emits `onData` for the terminal replies the CHILD elicits,
    // so a supervised CLI printing a cursor-position query could clear the very block that stops two
    // spoken sentences being submitted as one prompt the operator never said. The decision now lives
    // on `before-input-event`, the OS input path the child is not on. Nothing replaced it here: two
    // channels for one decision is how the wrong one stays reachable.
    return manager.write(id, data);
  });
  // Phase 16A: byte-exact scrollback replay on (re)attach. The SessionRegistry already holds the
  // exact bytes the PTY emitted (RingBuffer, invariant 27); this returns that snapshot plus the seq
  // of the last chunk it INCLUDES, read atomically on the main loop. The renderer's PaneFeed writes
  // the snapshot then only the live chunks newer than `seq` — no gap, no duplication. A pane with no
  // registered session (e.g. the conductor placeholder) returns an empty, honest {text:"",seq:-1}.
  ipcMain.handle("pane:scrollback", (_e, id) => {
    try {
      if (!manager || !manager.registry.has(id)) return { text: "", seq: -1 };
      const snap = manager.registry.reattach(id); // byte-exact Buffer; marks the view attached
      const seq = dataSeq.get(id);
      return { text: snap.toString("utf8"), seq: Number.isFinite(seq) ? seq : 0 };
    } catch (e) {
      return { text: "", seq: -1, error: `${e.name || "Error"}: ${e.message}` };
    }
  });
  // Fail-closed: a resize can race ahead of session admission (e.g. the pinned CONDUCTOR placeholder
  // pane carries no admitted session until its live launch — operator-run/16F), so guard on the
  // registry exactly as pane:scrollback does rather than throwing an unhandled TypeError.
  // Phase 17D `.close` (U73): the renderer's geometry report is an INTENT the main process decides
  // on — a pane with no admitted session (pane 1 before its governed launch), a resize that beats
  // supervision into existence, or numbers a ConPTY cannot take are all REFUSALS with a reason, and
  // none of them is an exception. The rule lives in panes/resize-intent.js so it is testable at all;
  // this handler must not re-grow one of its own (pane-resize.test.js pins that).
  // A refusal that is not the expected placeholder one is REPORTED (invariant 27): a live pane whose
  // resizes are being turned away is a fault the operator's log should carry, and the answer object
  // goes to a renderer that discards it. Once per pane per reason — the renderer fits continuously,
  // and a log that repeats itself sixty times a second is not observability either.
  ipcMain.handle("pane:resize", (_e, id, cols, rows) => {
    const answer = resizePane(manager, id, cols, rows);
    if (refusalWorthLogging(answer)) {
      const key = `${id}:${answer.reason}`;
      if (!resizeRefusalsLogged.has(key)) {
        resizeRefusalsLogged.add(key);
        log(`pane ${id}: resize to ${cols}x${rows} refused — ${answer.reason}`);
      }
    }
    return answer;
  });
  ipcMain.handle("pane:close", (_e, id) => { try { manager.kill(id); } catch { /* terminal */ } if (panes.panes.has(id)) panes.destroyPane(id); emptyPanes.delete(id); paneChrome.delete(id); persistLayoutSnapshot(); pushState(); });
  ipcMain.handle("pane:focus", (_e, id) => { panes.focus(id); pushState(); });
  ipcMain.handle("pane:maximize", (_e, id) => { panes.maximize(id); pushState(); });
  ipcMain.handle("pane:restore", (_e, id) => { panes.restore(id); pushState(); });
  ipcMain.handle("pane:minimize", (_e, id) => { panes.minimize(id); pushState(); });
  ipcMain.handle("pane:pin", (_e, id, on) => { on ? panes.pin(id) : panes.unpin(id); persistLayoutSnapshot(); pushState(); });
  ipcMain.handle("pane:activity", (_e, id, activity) => { panes.setActivity(id, activity); pushState(); });
  ipcMain.handle("shell:snapshot", () => panes.visible());

  // conductor-first pane (§13/§12.4): the CONDUCTOR badge + Resume→Select succession control. The
  // renderer draws pane-1's chrome from this; the governed live launch/succession are Python-side.
  ipcMain.handle("conductor:state", () => conductorState());
  ipcMain.handle("conductor:select", async (_e, selection) => selectConductorFromPicker(selection || {}));
  // Resume→Select reachable from the conductor chrome (§13.7): the operator requests a succession.
  // The real serialize/reconstruct/restore is control_plane.recovery.succession (the already-gated
  // 15D SuccessionManager); here the shell only surfaces that the control is reachable and RECORDS
  // the request. It NEVER self-authorizes a succession (invariant 1); actual delivery to the governed
  // succession path is deferred to a later 15E sub-step.
  // Phase 17A `.pty` (OP-11 §16 17A: "on launch AND via an explicit pane-1 control"): the operator
  // asks pane 1 to run its REAL interactive conductor session. The shell decides nothing — the
  // governed Python ticket does, and the supervised spawn path enforces admission. A refusal comes
  // back with its reason so the pane can say why it is still dark, never a silent no-op.
  ipcMain.handle("conductor:launch", async () => launchConductorSession({ reason: "operator control (pane 1)" }));
  ipcMain.handle("conductor:succeed", () => {
    const aff = conductorSuccessionAffordance() || {};
    const actions = Array.isArray(aff.actions) ? aff.actions : [];
    log(`conductor: operator requested Resume→Select (succession affordance: ${actions.join("→") || "unavailable"})`);
    return { requested: true, affordance: conductorState().succession };
  });

  // operator command surface (§12.5 item 5; Phase 16D `.approvals`, closes U66): READ the drawer model
  // SOURCED from the real ApprovalQueue.drawer_model(), and ROUTE an operator approve/reject back to the
  // GOVERNED authority. The decide NEVER self-authorizes (invariant 1): the shell forwards item+decision
  // to the Python ApprovalQueue.resolve (operator-only) which decides — approving a non-approvable
  // (gate-failed / clarification) item is refused there (invariant 16, no override). The shell records
  // the governed OUTCOME (resolved / governed-refused / unavailable), it never fabricates a resolution.
  ipcMain.handle("approvals:fetch", async () => refreshApprovalModel());
  ipcMain.handle("approvals:decide", async (_e, itemId, decision, reason) => {
    const d = decision === "approve" || decision === "reject" ? decision : "invalid";
    if (d === "invalid") return { recorded: false, error: "decision must be approve|reject" };
    const res = await routeApprovalDecision({ cwd: REPO_ROOT, itemId, decision: d, reason,
      eventsPath: sessionApprovals.path() });
    const governed = res.ok ? res.feed : null;
    // Phase 17D `.events`: persist the decision by APPENDING the event the AUTHORITY minted on its
    // resolve. The shell never authors a decision record — so it cannot record an approval Python did
    // not grant — and every later rebuild replays this through ApprovalQueue.resolve, which is what
    // makes a decided item stop coming back (and re-checks invariants 1/16 each time).
    if (governed && governed.resolved === true && governed.decision_event) {
      const recorded = sessionApprovals.recordGovernedDecision(governed.decision_event);
      if (!recorded) log(`approvals: the governed resolve of ${itemId} could NOT be recorded — it will `
        + "reappear as pending on the next fetch (fail-closed: nothing is claimed that was not written)");
    }
    // "RESOLVED (nothing executed)" — the governed authority recorded the operator's decision on the
    // immutable queue item and the resolve now persists, but the downstream side effect (broker
    // execute / ObjectiveIntake assign) is still not fired, so we do NOT claim it was "applied". The
    // operator is told the same thing in the drawer itself, not only in this log (17D `.events`).
    const outcome = res.ok ? (governed.resolved ? "RESOLVED (recorded; nothing executed — side effect owed 17E)" : governed.refused ? `REFUSED: ${governed.reason}` : `unavailable: ${governed.reason}`) : `unavailable: ${res.error}`;
    log(`approvals: operator ${d} of ${itemId || "(none)"}${reason ? ` — ${reason}` : ""} → governed resolve ${outcome}`);
    // self-authorized:false is the load-bearing property — the shell forwarded; Python authority decided.
    return { recorded: true, itemId: itemId || null, decision: d, routed: res.ok, selfAuthorized: false,
      governed, error: res.ok ? undefined : res.error };
  });

  // conductor voice-IN (§13.5; Phase 16E `.wire`, closes the WRITE half of U67): READ the mic
  // affordance/state (with the VISIBLE mock/real engine indicator), and CAPTURE — source the
  // engine-selected conductor_voice_feed@1.0 through the REAL bridge, then route by the bridge's
  // verdict. The shell self-authorizes NOTHING (invariant 1): a CHAT is delivered into the conductor
  // input (same command path as typing), a PROTECTED/DESTRUCTIVE action is QUEUED for approval (never
  // delivered — invariant 25; it surfaces in the drawer), a low-confidence transcript CLARIFIES. The
  // STT engine is mock until the WSL Parakeet path lands (`.real`), ALWAYS surfaced visibly. The
  // interactive conductor ConPTY drive is operator-run (§6): with no admitted conductor session, a
  // routed CHAT is honestly OWED to 16F, never fabricated as delivered. Fail-closed on any fault.
  ipcMain.handle("voice:state", () => voiceState());
  // Phase 17C `.probe` (U74): re-probe ON DEMAND. `voice:probe` starts one if the answer is stale and
  // resolves when it lands; `{force:true}` re-takes it now — the operator's retry after finishing the
  // WSL install, and the after-failure path that the old lifetime cache made impossible. It never
  // throws: a fault settles as `unavailable` with the reason named.
  ipcMain.handle("voice:probe", async (_e, opts) => {
    const p = ensureVoiceProbe();
    // The renderer is the least-trusted surface (invariant 29): a forced re-probe spawns a WSL NeMo
    // import, so an unmetered `{force:true}` loop would be a continuous host-resource drain driven from
    // the sandbox. Rate-limited here; a refused force degrades to the ordinary (cached) read, never an
    // error — the operator's click still gets an honest answer.
    const now = Date.now();
    const wanted = Boolean(opts && opts.force);
    const allowed = wanted && (lastForcedProbeAt == null || now - lastForcedProbeAt >= FORCED_PROBE_MIN_INTERVAL_MS);
    if (allowed) lastForcedProbeAt = now;
    const state = await (allowed ? p.refresh() : p.start());
    pushVoice();
    return { state: state.state, reason: state.reason, elapsed_ms: state.elapsedMs,
             probes: state.probeCount, forced: allowed,
             throttled: wanted && !allowed ? `a forced re-probe is allowed every ${FORCED_PROBE_MIN_INTERVAL_MS}ms` : undefined,
             engine: voiceEngineDescriptor() };
  });
  // `payload` is EITHER a legacy stand-in ref string (`"audio:show-status"` — the indicator poll and
  // the pre-`.mic` self-checks) OR, since Phase 17C `.mic`, `{pcm, sampleRate}` carrying real
  // microphone bytes from the renderer. The two paths differ in exactly one governed way: real PCM
  // selects the REAL engine and is written to (and then deleted from) disk; a stand-in never can.
  ipcMain.handle("voice:capture", async (_e, payload) => {
    const hasPcm = payload && typeof payload === "object" && payload.pcm != null;
    // The cap is enforced HERE, in main, because the renderer's own serialisation is not a control
    // (invariant 29). A refused capture is an honest fail-closed feed, never an error and never a
    // fabricated delivery — and never a queue, because a queued utterance would reach the conductor
    // long after the operator stopped expecting it.
    if (capturesInFlight >= MAX_CONCURRENT_CAPTURES) {
      const reason = "a capture is already in progress — one at a time (there is one microphone)";
      log(`voice: capture REFUSED — ${reason}`);
      return foldCapture({ ok: false, error: reason, feed: unavailableVoiceFeed(reason) },
        { real_pcm: hasPcm, refused: true }, "refused (already capturing)");
    }
    capturesInFlight += 1;
    pushVoice();   // U133: the chrome says "listening" for the whole real round trip, not after it
    try {
      return hasPcm ? await captureFromPcm(payload) : await captureFromRef(payload || undefined);
    } finally {
      capturesInFlight = Math.max(0, capturesInFlight - 1);
      pushVoice();
    }
  });

  // The stand-in path, unchanged: a scripted `audio:` ref carries no PCM, so the bridge routes it
  // through the visible mock. Kept because the engine-state poll and the honesty negatives (a
  // PROTECTED verb must queue, not deliver) do not need — and must not need — a microphone.
  async function captureFromRef(audioRef) {
    const src = await sourceConductorVoiceFeed({ cwd: REPO_ROOT, audioRef: audioRef || undefined });
    return foldCapture(src, { real_pcm: false, audio_ref: audioRef || null }, audioRef || "(default)");
  }

  /**
 * Phase 17C `.mic`: REAL operator speech. Write the bytes, transcribe through the real engine, and
 * delete the file — the delete guaranteed by `withCapture`'s `finally` on every path (invariant 26).
   *
 * The renderer is the least-trusted surface (invariant 29): `CaptureStore.write` refuses anything
 * that is not a bounded RIFF/WAVE before it touches disk, and a refusal is reported as the honest
 * fail-closed feed — never a fabricated delivery, and never a silent fall-back to the mock, which
 * would be a pretend-to-hear on the one path where the operator really did speak.
   */
  async function captureFromPcm(payload) {
    const store = ensureCaptureStore();
    // `ensureFresh()` rather than `state()`: an expired positive is the last established fact, but
    // seeding it as if current would stamp a stale answer with a fresh timestamp and a provenance
    // string that says nothing about its age. A stale answer is used but NOT seeded — the emitter then
    // establishes it properly, which is the fail-closed direction.
    const probe = ensureVoiceProbe().ensureFresh();
    const seedable = probe.state === "available" && probe.stale !== true;
    let capture = null;
    try {
      const run = await store.withCapture(payload.pcm, async (wavPath, written) => {
        capture = written;
        return sourceConductorVoiceFeed({
          cwd: REPO_ROOT,
          audioRef: wavPath,
          realCapture: true,
          // the answer the shell already established (U134) — a cache seed, never a claim: the WSL
          // round trip below still fails closed if NeMo is not really there.
          engineState: seedable ? { state: probe.state, reason: probe.reason, elapsedMs: probe.elapsedMs } : null,
        });
      });
      const feed = (run.result && run.result.feed) || {};
      // Awaited INSIDE the try (rather than returning the promise) so a fault in the delivery fold is
      // caught below and reported as the honest failed capture — with what the guaranteed discard did.
      return await foldCapture(run.result, {
        real_pcm: true,
        bytes: capture ? capture.bytes : 0,
        // the DECODED facts about the bytes, not the renderer's claim about its own payload: a junk
        // `sampleRate` would otherwise be recorded as truth in the receipt, and a negative one would
        // throw out of `durationSeconds` AFTER a good transcription and lose the transcript.
        sample_rate: capture ? capture.sampleRate : null,
        seconds: capture ? Math.round(capture.seconds * 1000) / 1000 : 0,
        // load-bearing for invariant 26: what the discard actually did, not what it intended
        discarded: run.discard.discarded === true,
        discard_reason: run.discard.reason || null,
        // the EMITTER's own report that the seed arrived and was applied — the shell's local intent
        // (`seedable`) cannot observe the far side of the process seam, and this leg exists to.
        engine_state_seeded: feed.engine_state_seeded != null && feed.engine_state_seeded.seeded === true,
        engine_state_offered: seedable,
      }, `${capture ? capture.bytes : 0} bytes of live PCM`);
    } catch (e) {
      // REDACTED: an fs/write error embeds the capture path, and this reason reaches the renderer, the
      // shell log and the committed receipt. The code is what a reader needs; the location is not.
      const reason = redactCapturePaths(e instanceof CaptureStoreError
        ? `captured audio refused: ${e.message}`
        : `${e.name || "Error"}: ${e.message}`);
      log(`voice: real capture failed — ${reason}`);
      const d = store.lastDiscard;
      return foldCapture({ ok: false, error: reason, feed: unavailableVoiceFeed(reason) },
        { real_pcm: true, bytes: capture ? capture.bytes : 0,
          // a throw does not excuse retained audio: report what the guaranteed discard managed.
          // Explicitly boolean — this field answers "was the operator's audio deleted?" and a null
          // there is not an answer.
          discarded: capture ? (d ? d.discarded === true : false) : true,
          discard_reason: (d && d.reason) || null },
        "live PCM (failed)");
    }
  }

  // The shared fold: route by the BRIDGE's verdict, deliver only a CHAT, log, repaint. Identical for
  // both paths, so a real capture can never take a shortcut a stand-in cannot.
  async function foldCapture(src, captureMeta, label) {
    const feed = src.feed; // sourceConductorVoiceFeed never throws — a fault yields the unavailable feed
    lastVoiceFeed = feed;
    // Phase 17D `.events`: an utterance the governed bridge did NOT deliver as chat — a protected verb
    // the broker queued, or a transcript it would not route — is the operator's to decide, so it is
    // recorded for the drawer. A CHAT records nothing (it reached the conductor; there is nothing to
    // approve), and the recorded classification is a claim the Python builder re-derives, never a
    // verdict this process gets to assert.
    const recorded = sessionApprovals.recordUtterance(feed, { channel: "voice:capture" });
    if (recorded) {
      log(`approvals: recorded ${recorded.utterance.classified_as} from ${recorded.utterance.source} `
        + `as ${recorded.event_id} — it is now in the approval drawer`);
      refreshApprovalModel().then(() => pushApprovals()).catch(() => {});
    }
    const decision = decideDelivery(feed);
    let write = { written: false, submitted: false, reason: decision.reason };
    if (decision.shouldDeliver) {
      const turn = { utc: new Date().toISOString(), dir: "out", text: decision.text,
        channel: "voice", delivered: false, submitted: false };
      pushTranscriptTurn(turn);
      write = await deliverConductorConversation(decision.text);
      turn.delivered = write.written === true;
      turn.submitted = write.submitted === true;
      recordConversationContext(turn, write);
    }
    lastVoiceWrite = write;   // the badge is drawn from this too (never from the routing verdict alone)
    const result = buildCaptureResult(feed, write);
    result.capture = captureMeta;
    const kind = (feed.outcome && feed.outcome.kind) || "clarify";
    const audioRef = label;
    log(`voice: operator push-to-talk (audio ${audioRef}) → ${kind}`
      + `${result.delivered_to_conductor ? " delivered to conductor input" : ` (${write.reason})`}`
      + `${feed.engine && feed.engine.mock ? " [mock engine]" : ""}`
      + `${captureMeta.real_pcm ? `${captureMeta.discarded ? " [audio discarded]" : " [AUDIO NOT DISCARDED]"}` : ""}`);
    // Phase 17C `.probe`: repaint the chrome from this capture. `result.engine` stays the CAPTURE's own
    // engine descriptor (what actually transcribed this utterance — the honest per-utterance fact); the
    // chrome-level reconciliation with the probe happens in `voiceEngineDescriptor()`, so a mock
    // stand-in capture can never close a question the probe has not answered, and neither record is
    // rewritten by the other.
    pushVoice();
    // self-authorized:false is load-bearing — the shell forwarded the bridge's verdict, it decided nothing.
    return { ...result, chromeEngine: voiceEngineDescriptor(), selfAuthorized: false,
             sourced: feed.sourced === true, error: src.ok ? undefined : src.error };
  }

  // Routing/artifact inspector (Plan §10.3): READ-ONLY over the same authenticated IPC channel.
  // Fail-closed and observable — if the control-plane channel is not up, the renderer is told so
  // explicitly (a structured {ok:false}) rather than shown a stale or fabricated model. The panel
  // that draws this is an operator-run surface (like the window); the data path is headlessly
  // proven in apps/desktop/test/inspector-source.test.js against a real seeded MCP server.
  ipcMain.handle("inspector:fetch", async () => {
    const nodes = [operationalConductorStatus(), ...liveWorkerRecords().map(operationalNodeStatus)]
      .filter(Boolean);
    const operational = await fetchOperationalState({ cwd: REPO_ROOT, projectId: "proj",
      storeRoot: sowStoreRoot(), nodes });  // F-131
    let legacy = null;
    let legacyError = null;
    try {
      if (!ipcClient) throw new Error("control-plane channel not established");
      const { model, summary, routingReadable } = await fetchInspectorModel(ipcClient);
      legacy = { model, summary, routingReadable };
    } catch (e) {
      legacyError = `${e.name || "Error"}: ${e.message}`;
    }
    // U336 (unit 19.7): the top-level `ok` is the honest AND of the two reads. It used to be the
    // literal `true` whenever the LEGACY read succeeded, so an inspector whose live-orchestration
    // half had failed answered `ok:true` and the drawer painted the failure's zero counts as state.
    // `ok:false` here does not mean "show nothing": the payload is still carried, `operational`
    // still says `available:false` with its reason, and the renderer paints what is readable under a
    // banner naming what is not. Fail closed on the CLAIM, not on the operator's visibility.
    const operationalOk = operational.available === true;
    if (!legacy && !operationalOk) {
      return { ok: false, error: `${legacyError}; ${operational.error}` };
    }
    const unreadable = [legacy ? null : legacyError,
      operationalOk ? null : `live orchestration: ${operational.error}`].filter(Boolean);
    return {
      ok: Boolean(legacy) && operationalOk,
      error: unreadable.length ? unreadable.join("; ") : undefined,
      operational, legacyError,
      // …and the same rule for the OTHER half. An unreadable control-plane channel used to be
      // rendered as an empty model with a five-zero summary; it is null, and the drawer says so.
      model: legacy ? legacy.model : null,
      summary: legacy ? legacy.summary : null,
      routingReadable: legacy ? legacy.routingReadable : false,
    };
  });

  // Subscription-concurrency status bar (directive §11 track 15A; Phase 16D `.statusbar`, OP-10): the
  // n/allowance count per live provider. The operator saw "concurrency count unavailable" because the
  // shell's gateway is the diagnostic EchoControlSurface, which does not expose the subscription_status
  // op — so the tested IPC read path (statusbar/source.js, still the design endpoint for a governor-
  // backed gateway at 16F) had nothing to read. `.statusbar` SOURCES the count from the REAL governor
  // via a bounded read-source (statusbar/governor-source.js → tools/live/emit_subscription_status.py),
  // seeded from the enforced LiveAuthorization — the SAME §6 substitution the 16B picker and the 16C
  // conductor feeds use (a bounded py -3.12 emitter, not the WS-IPC channel; recorded in evidence).
  // Always visible ⇒ never throws: any fault, or an unauthorized feed, degrades to the fail-closed
  // em-dash unknown (no fabricated 0/2). HONEST scope (§10.4): the count is the authorized ceiling +
  // terminals held by this shell NOW (0 — live drive is operator-run/16F); dynamic per-session
  // tracking is owed to 16F. DATA path proven in apps/desktop/test/statusbar-governor-source.test.js
  // + the in-Electron self-check; the rendered bar is an operator-run surface.
  ipcMain.handle("statusbar:fetch", async () => fetchStatusBarModelFromGovernor({ cwd: REPO_ROOT }));

  // Per-pane model picker (Phase 16B; OP-7 §12.2 / OP-10 §15 track 16B) — READ the live host
  // enumeration. The option set is produced by the ONE authority (tools/live/enumerate_pane_picker
  // --emit-picker); this shell renders it verbatim and never fabricates an option. Fail-closed:
  // any enumeration fault returns {ok:false, picker: emptyPicker}, so the dropdown shows
  // "unavailable" rather than a guessed model. Read-only — no credential, no model call (§2.2/§2.4).
  ipcMain.handle("picker:fetch", async () => { lastPickerModel = await fetchPickerModel({ cwd: REPO_ROOT }); return lastPickerModel; });

  // Phase 17B `.spawn` (closes U70's spawn half; operator finding F3): a picker selection now LAUNCHES.
  // The handler asks Python for a governed `worker_launch_ticket@1.0` (the whole gate chain:
  // host-enumeration verification, live authorization, R8 terms, CLI presence, I-X3 durable lease for
  // a frontier model / ResidencyPlanner admission for a local one) and, only if one is ISSUED, spawns
  // that exact argv in the pane's ConPTY through the supervised SessionManager, under the
  // Python-minted node identity, in the authorized workspace, with the named credential vars dropped
  // (§2.2). A refusal starts nothing and is surfaced verbatim. The comment below records what this
  // path USED to be — a recorded selection with no execution — because that is the defect it closes.
  // Everything from here to the handler is that HISTORICAL note, kept for the record and no longer
  // a description of this path: it is written in the present tense and its claims ("RECORDS the
  // governed selection", "never claims a live node exists", "live drive is operator-run / gate 16F")
  // are all false of the shell as it now stands (spec-audit MINOR-6).
  //
  // HISTORICAL (16B): Selection → the governed pane_node_spawn path. The AUTHORITY is Python-side:
  // node_runtime/supervisor/pane_node_spawn.spawn_node_from_selection (already gated + tested at
  // 15E `.spawn`) turns one selected option into a supervised, I-X3-governed / residency-planned
  // spawn or a fail-closed refusal. A LIVE governed spawn is an IPC WRITE (gated by the per-node
  // credential broker, U25) and a live model process (mock-first §2.4/§10.4; live drive is
  // operator-run / gate 16F). So — exactly as conductor:succeed / approvals:decide / voice:propose
  // RECORD-without-executing — this intent runs the SAME fail-closed selection guard the Python
  // dispatcher enforces (defense-in-depth: greyed / bad-role / unknown-mode / conductor-role are
  // refused here AND re-checked there), RECORDS the governed selection, and returns the pane chrome
  // preview (model badge + subscription/residency) the renderer draws. It self-authorizes NOTHING
  // (invariant 1) and starts no naked session (invariant 2); it never claims a live node exists.
  ipcMain.handle("pane:spawnFromSelection", async (_e, selection) => spawnFromSelection(selection || {}));
}

// Build the pane chrome from the SELECTED option, verbatim — the badge can never diverge from what
// the operator picked. Used for the NON-launched outcomes only: `node_state` names the launch
// outcome (refused / unavailable / failed) and carries the governed reason, so a badge is never
// again a promise of a spawn that is not coming (operator finding F3). A LAUNCHED pane's chrome is
// the TICKET's chrome — Python's, not this one. n/2 for a frontier option is the allowance from the
// live authorization; the live in-use count is the always-on status bar's, never fabricated here.
//
// `model_verified` is the ONE field here that is not the operator's own choice but a CLAIM about a
// model: `verified` means a live smoke reported that checkpoint (invariant 3). It is therefore read
// from the HOST's enumeration by slug, never from the option the renderer handed in — the renderer
// is the least-trusted surface (invariant 29) and a forged option carrying `verified:true` used to
// badge a refused pane with a verification this host never made (spec-audit MINOR-7). Python closed
// the same hole on the issue path by returning the host's own option; this is the refusal path.
function chromePreview(sel, auth, { nodeState, reason = null, refusedBy = null } = {}) {
  const o = sel.option;
  const frontier = o.locality === "frontier";
  return {
    provider: o.provider, adapter: o.adapter, locality: o.locality,
    model_label: o.label, model_slug: o.model_slug || null, model_verified: hostVerifiedFlag(o),
    role: sel.role, mode: sel.mode,
    node_state: nodeState || "launch_unavailable",
    governed: false, launch_reason: reason, launch_refused_by: refusedBy,
    // PER-PROVIDER allowance (OP-12 §12): after the two 1-terminal subscriptions exist, the global
    // number overstates their ceiling. `terminals_by_provider` comes from LiveAuthorization.as_dict();
    // fall back to the global figure only when the per-provider view is absent (older feed shape),
    // and to null when neither is — never to an invented number.
    subscription: frontier ? { allowance: providerAllowance(auth, o.adapter), in_use: null } : null,
    residency: frontier ? null : (o.residency || null),
  };
}

// The allowance to display for ONE provider's subscription. Reads the per-provider view first
// (OP-12 §12 caps grok_build/google_antigravity at 1 while the config's global figure is 2), then
// the global figure, then null. Never fabricates: an unknown provider shows the em-dash, not a 2.
function providerAllowance(auth, adapter) {
  if (!auth) return null;
  const byProvider = auth.terminals_by_provider;
  if (byProvider && Object.prototype.hasOwnProperty.call(byProvider, adapter)) {
    return byProvider[adapter];
  }
  return auth.terminals_per_subscription || null;
}

// Is this model VERIFIED, according to the host's own enumeration? Matched by (adapter, slug) against
// the last picker model this shell sourced from Python. Fail-closed: an option this host does not
// currently offer — a fabricated one, or a stale one — is NOT verified, whatever the caller claimed.
function hostVerifiedFlag(o) {
  const options = (lastPickerModel && lastPickerModel.picker && lastPickerModel.picker.options) || [];
  const match = options.find((h) => h && h.adapter === o.adapter && h.model_slug === o.model_slug);
  return Boolean(match && match.verified === true);
}

// The pane a selection launches into: the operator's target pane if it exists, else a NEW pane id.
// The pane itself is not created here — `spawnSession` below creates it only once a governed
// authorization has actually been obtained, so a refused selection never leaves a blank pane behind.
function resolveTargetPaneId(selection) {
  const target = selection.targetPaneId || null;
  return target && panes.panes.has(target) ? target : `pane-${++paneSeq}`;
}

// The GOVERNED worker-pane launcher (Phase 17B `.spawn`, closes U70's spawn half). Every rule lives
// in picker/worker-spawn.js so the headless suite covers it; this is the wiring to the real shell:
// the supervised SessionManager spawn, the pane model, the live admission state, and this process's
// env — which is also the env whose var NAMES are sent for classification (U105).
let workerLauncherInstance = null;
function workerLauncher() {
  if (workerLauncherInstance) return workerLauncherInstance;
  workerLauncherInstance = createWorkerPaneLauncher({
    repoRoot: REPO_ROOT,
    holderPid: process.pid,
    baseEnv: process.env,
    timeoutMs: PROCESS_STARTUP_TIMEOUT_MS,
    isSupervised: () => Boolean(supervisor && supervisor.ready && manager),
    // `registry.get` THROWS on an unknown session, so occupancy is asked with `has` first: a pane
    // that has never held one is FREE, not an error. The state test is `isTerminal` — the registry's
    // own notion of "ended" — rather than a locally maintained list of terminal state names, which
    // would silently start reading a new state as LIVE (and refuse every launch into that pane).
    hasLiveSession: (paneId) => Boolean(manager && manager.registry.has(paneId)
      && !manager.registry.isTerminal(paneId)),
    // A record from a session that already ENDED must not wedge the pane for the rest of the shell's
    // life (the same rule pane 1 follows). The registry REFUSES to forget a LIVE session, so this can
    // never orphan a supervised process — it throws, and the launch is refused.
    forgetSession: (paneId) => { if (manager && manager.registry.has(paneId)) manager.forget(paneId); },
    // G22: governed replacement teardown - identical primitive to pane:close.
    endLiveSession: (paneId) => { if (manager) manager.kill(paneId); },
    // The supervised spawn + its post-spawn ROLLBACK (spec-audit MAJOR-3) live in picker/pane-wiring.js
    // so the headless suite drives them: written here they were correct and untestable, and reverting
    // the rollback left every suite green (spec-audit MAJOR-2). Bound per call rather than once,
    // because `manager` is assigned during bootstrap: capturing it at launcher-construction time
    // would freeze whatever it was then, and a null capture would fail as a TypeError rather than as
    // the module's own fail-closed refusal.
    spawnSession: (args) => createGovernedPaneSpawn({
      manager, panes, persistLayoutSnapshot, pushState, emitLayoutNow, log,
    })(args),
    // A spawn result is not itself proof that supervision remains registered. Re-observe the exact
    // pid/generation after birth; worker-spawn records `supervised:false` when this is absent/stale.
    processIdentity: (paneId) => (manager ? manager.processIdentity(paneId) : null),
    augmentSpawnEnv: (env, ctx) => {
      if (!sovereignControl || !sovereignControl.port) {
        throw new Error("Sovereign application-control MCP gateway is not ready");
      }
      const chrome = (ctx.ticket && ctx.ticket.chrome) || {};
      return sovereignControl.childEnv({
        node_id: ctx.identity.node_id, role: "worker", project_id: "proj",
        provider_id: chrome.provider || null, model_id: chrome.model_slug || null,
        pane_id: ctx.paneId, session_id: ctx.sessionId,
        store_root: sowStoreRoot(),  // F-131
      }, env).env;
    },
    revokeNodeControl: (nodeId) => { if (sovereignControl) sovereignControl.revokeNode(nodeId); },
    onChange: () => pushState(),
    log,
  });
  return workerLauncherInstance;
}

/** The observable per-pane worker launch state (invariant 27) — read by the self-check and the UI. */
function workerLaunchState(paneId) { return workerLauncher().record(paneId); }

/**
 * A governed worker pane's session ended (exit, operator close, or the fail-closed kill on
 * supervision loss): its chrome must say so. The model badge is KEPT — the operator picked it and it
 * is still what that pane last ran — but `node_state`/`governed`/`pid` describe a node that no
 * longer exists, so they are corrected here and the corrected chrome is what the layout snapshot
 * (and therefore the next boot's recovery view) carries.
 */
function markWorkerPaneChromeEnded(event) {
  const id = event && event.id;
  // The RULE is `endedWorkerChrome` in picker/pane-wiring.js (pure, headlessly tested); this is the
  // wiring only. It was written inline here and no test or receipt leg could see it — reverting it
  // left every suite green (spec-audit MAJOR-2).
  const ended = endedWorkerChrome(id ? paneChrome.get(id) : null, event || {});
  if (!ended) return;
  paneChrome.set(id, ended);
  persistLayoutSnapshot();
  // …and the RENDERER's copy, or the operator's badge keeps reading `live` for a dead pane while the
  // shell knows better — the server-side correction alone would fix only what a restart shows.
  if (win && !win.isDestroyed()) win.webContents.send("pane:chrome", id, ended);
  pushState();
  pushConductor();
}

/**
 * A picker selection → a LIVE governed worker session in a pane (Phase 17B `.spawn`).
 *
 * 16B recorded the selection, badged the pane and started nothing — the operator's finding F3. The
 * authority is unchanged and still Python's: `emit_worker_launch.py` runs the whole gate chain and
 * either issues an executable ticket or refuses. This handler executes an issued ticket and records
 * a refusal verbatim; it self-authorizes nothing (invariant 1) and never spawns a session that was
 * not authorized and admitted (invariant 2).
 */
async function spawnFromSelection(selection) {
  // W-37: the guard is handed the LIVE host enumeration so it can corroborate the selection rather
  // than believe it — the same `lastPickerModel` the conductor pre-launch path and
  // `hostVerifiedFlag` already consult.
  const reason = refuseSelection(selection, {
    conductorPaneId,
    hostOptions: (lastPickerModel && lastPickerModel.picker && lastPickerModel.picker.options) || [],
  });
  if (reason) {
    log(`picker: spawn REFUSED (fail-closed) — ${reason}`);
    return { recorded: false, launched: false, error: reason };
  }
  const o = selection.option;
  const auth = (lastPickerModel && lastPickerModel.picker && lastPickerModel.picker.authorization) || null;
  const paneId = resolveTargetPaneId(selection);
  log(`picker: operator selected ${o.provider}/${o.label} role=${selection.role} `
    + `mode=${selection.mode} target=${paneId} — requesting a governed launch`);
  const res = await workerLauncher().launchWorkerPane({
    paneId,
    selection: { option: o, role: selection.role, mode: selection.mode },
  });
  const rec = res.record || {};
  // The LAUNCHED pane's chrome is the ticket's (Python's), with the one fact this shell owns added:
  // the session is running and this is its pid. A non-launched pane gets the honest preview naming
  // the outcome. Either way the chrome is recorded server-side keyed by paneId so paneMeta() → the
  // layout snapshot → a restart repaints the exact badge (16D `.recovery`, U68).
  //
  // A refusal that left a LIVE session untouched (`heldSessionUntouched` — the operator clicked the
  // picker on a pane that is already running one) must NOT repaint that pane: writing the refusal
  // chrome there reported a live, supervised, Python-authorized node as `launch_refused` /
  // `governed:false`, persisted it into the last-good layout, and repainted the badge — a running
  // node described as dark (validator MAJOR-1, invariants 3/27). The refusal is still returned in
  // full; the pane keeps the chrome of what it is actually running.
  const chrome = res.launched
    ? { ...(rec.chrome || {}), node_state: "running", governed: true, pid: rec.pid || null,
      session_generation: rec.sessionGeneration,
      launch_reason: null, launch_refused_by: null }
    : res.heldSessionUntouched
      ? (paneChrome.get(paneId) || null)
      : chromePreview(selection, auth, {
        nodeState: rec.state === "refused" ? "launch_refused"
          : rec.state === "failed" ? "launch_failed" : "launch_unavailable",
        reason: res.reason || null, refusedBy: res.refusedBy || null,
      });
  if (panes.panes.has(paneId) && !res.heldSessionUntouched) {
    paneChrome.set(paneId, chrome);
    persistLayoutSnapshot(); // capture the badge into the LAST GOOD layout for the next boot
  }
  // The identity fields describe THIS attempt. On the `heldSessionUntouched` path the launcher
  // deliberately returns the RUNNING session's record (that is how it proves it left it alone), so
  // reporting `rec.sessionId`/`nodeId`/`argv`/`state` here would hand the caller another session's
  // identity labelled as this click's result — `launched:false` next to `state:"running"`
  // (spec-audit MINOR-5). This attempt started nothing and has no identity; it says so, and the
  // untouched session is reported under its own name so the fact is not lost either.
  const own = res.heldSessionUntouched ? null : rec;
  return {
    recorded: true, launched: res.launched === true, chrome, target: paneId,
    state: own ? own.state || null : null,
    sessionId: own ? own.sessionId || null : null,
    nodeId: own ? own.nodeId || null : null,
    argv: own ? own.argv || null : null,
    heldSessionUntouched: res.heldSessionUntouched === true,
    heldSessionId: res.heldSessionUntouched ? rec.sessionId || null : null,
    reason: res.reason || null, refusedBy: res.refusedBy || null,
    error: res.launched ? null : (res.reason || null),
    note: res.launched
      ? "LIVE governed worker session running in the pane under a Python-issued launch ticket "
        + "(supervised admission, workspace cwd, credential-scrubbed env, I-X3 counted for a frontier "
        + "model / VRAM-residency admitted for a local one)"
      : "no session was started — the governed reason is carried verbatim (fail closed)",
  };
}

// ---- standard MCP application-control surface ------------------------------
// Role checks, deadline state and the HTTP application-control handlers are built below from the
// require-able control/application-control.js module. What remains here is only live shell binding.

function operationalDispatchSummary() {
  return operationalState.operationalDispatchSummary();
}

const operationalState = createOperationalState({
  repoRoot: REPO_ROOT,
  workerRecords: () => (workerLauncherInstance ? workerLauncher().records() : []),
  chromeFor: (paneId) => paneChrome.get(paneId),
  mcpState: (nodeId) => (sovereignControl
    ? sovereignControl.connectionState(nodeId) : { state: "disconnected", last_seen: null }),
  sessionEstablished,
  normalizedProvider,
  conductorLaunch: () => conductorLaunch,
  conductorDescriptor,
  conductorPaneId: () => conductorPaneId,
});
const {
  liveWorkerRecords, operationalConductorStatus, operationalNodeStatus, workerRecordFor,
} = operationalState;

async function waitForNodeMcp(nodeId, timeoutMs = 120000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (sovereignControl && sovereignControl.connectionState(nodeId).state === "connected") return true;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return false;
}

// U329 (unit 19.4): the ONE reader readiness may use. `paneScreen()` — which returned
// `buffer.snapshot()`, the whole 256 KB scrollback — is gone: it is what made a dismissed overlay
// permanent and what let the shell's own echoed objective classify the worker it was sent to. This
// hands the module the RingBuffer itself so the bound is `sliceFrom()`'s, fail-closed, and no caller
// can widen it by passing a bigger string.
const readinessWindow = createScreenWindow({
  bufferFor: (paneId) => (manager && manager.registry.has(paneId)
    ? manager.registry.get(paneId).buffer : null),
});

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// U328: everything the SYSTEM types into a pane goes through here. The two bindings that could be
// got wrong (is the screen readable at all; which provider's rules apply) are the module's, because
// this file cannot be required in a test (U338) — a hand-rolled reader that always claimed the
// screen was legible would open the gate for every pane with nothing able to see it.
// U373 residual (unit 19.4-followon): the gate's own read is the SAME bounded window object
// readiness classifies through — `readinessWindow`, one line up, passed by reference. Not a second
// reader with the same bounds: two readers drift, and a gate reading the whole 256 KB scrollback is
// exactly what left a healthy connected worker's prompt undeliverable.
const paneProviderFor = paneProviderResolver({
  chromeFor: (paneId) => paneChrome.get(paneId),
  conductorPaneId: () => conductorPaneId,
  conductorProvider: () => (conductorDescriptor() || {}).provider_id || null,
});

const paneWriter = createPaneWriter({
  paneScreen: paneScreenFromWindow(readinessWindow),
  providerFor: paneProviderFor,
  write: (paneId, data) => (manager ? manager.write(paneId, data) : false),
  sleep: pause,
  pasteSettleMs: () => PROVIDER_PASTE_SETTLE_MS,
  submitConfirmMs: () => CODEX_SUBMIT_CONFIRM_MS,
  log,
  conductorTarget: () => (conductorLaunch.nodeId && conductorLaunch.state === "running"
    ? { nodeId: conductorLaunch.nodeId, paneId: conductorPaneId } : null),
  workerPaneFor: (nodeId) => {
    const rec = workerRecordFor({ node_id: nodeId });
    return rec ? rec.paneId : null;
  },
});

// Thin Electron bindings consumed by the require-able application-control module and readiness.
async function writePanePrompt(paneId, prompt) {
  return (await paneWriter.writePrompt(paneId, prompt)).written;
}

async function notifyNode(nodeId, prompt) {
  return paneWriter.notifyNode(nodeId, prompt);
}

/**
 * Delegate one task to one LOCAL worker pane and read its answer back (EPC-03 L5-3/L5-4).
   *
 * WHY THIS EXISTS SEPARATELY FROM `assign_task`. That path writes a task and then waits for the
 * worker to call `publish_candidate` over MCP, which is right for a frontier coding agent that
 * has the Sovereign tools wired in. A pane running `ollama run llama3.2:3b` is a bare REPL: it
 * has no tools, it cannot call `publish_candidate`, and it never will. A local worker was
 * therefore assignable and could never complete an assignment, because completion was defined
 * as a call it cannot make.
   *
 * So the shell reads the answer off the pane and publishes it on the pane's behalf. The
 * candidate is marked `self_published: false` / `source: "observed_pane_output"` — weaker
 * evidence than a node's own publication, and recorded as such rather than smoothed over.
   *
 * `paneWriter.writePrompt` is passed, NOT `writePanePrompt`: the latter collapses the writer's
 * record to its boolean, and the U328 refusal REASON is exactly what a delegation must surface.
 * A withheld write has to be distinguishable from a pane that simply said nothing.
   *
 * This does NOT make a worker leg live. `_assert_legs_honest` and `build_acceptance_packet`
 * remain the only things that may say a worker executed anything, and neither is touched here
 * (L5-5, parked with its dossier).
 */
async function delegateToWorkerPane(paneId, nodeId, task, options = {}) {
  // Read-side count only: the existing delegation, journal writes and returned result are unchanged.
  let countedJournal = null;
  try { countedJournal = runtimeJournal(); } catch { /* journal absence belongs to the existing path */ }
  const countedSession = countedJournal && countedJournal.sessionId;
  const result = await delegateToPane({
    window: readinessWindow,
    writePrompt: (id, body) => paneWriter.writePrompt(id, body),
    sleep: pause,
    log,
  }, { paneId, nodeId, task, ...options });
  if (countedJournal) answerTally.note(countedJournal, countedSession, paneId, result);
  return result;
}

/**
 * THE LOOP, joined (EPC-03). Operator objective -> governed dispatch -> delegation -> candidates.
 *
 * The two halves have both worked for a while and were never connected. Typing reached the
 * CONDUCTOR's pane as text (`deliverConductorChat`); the governed dispatch ran once at launch over
 * the emitter's own fixed smoke objective and never saw anything the operator asked for. So the
 * DISPATCH line named real panes while reflecting no input, and `delegateToPane` sat wired and
 * uninvoked.
 *
 * EXPLICIT, NOT AUTOMATIC. This is not hung off `conductor:operator-text`. Every message the
 * operator types is not an objective — most are conversation — and decomposing each one would
 * spend model time on the operator's behalf without being asked, which is the rule an app launch
 * already obeys. The operator says when a message is work.
 *
 * WHAT IT DOES NOT DO. It does not make a worker leg live: `_assert_legs_honest` and
 * `build_acceptance_packet` remain the only things that may say a worker executed anything, and
 * neither is touched. Every candidate it returns is marked `self_published: false` /
 * `source: "observed_pane_output"`, because the shell READ it off a pane rather than the node
 * having ASSERTED it. L5-5 is parked and this does not quietly close it.
 *
 * Fail-closed at every step: a dispatch that will not run, an assignment naming no live pane, and
 * a pane whose write gate refuses are each REPORTED, never worked around.
 */
async function runObjective(objective, options = {}) {
  if (options && options.new_session === true) {
    const rotated = startJournalSession();
    conductorTranscript.length = 0;
    try {
      const w = Array.from(require("electron").BrowserWindow.getAllWindows())[0];
      if (w && !w.isDestroyed()) w.webContents.send("shell:conductor-transcript", []);
    } catch { /* no window yet */ }
    return { ok: true, deleted: false, ...rotated };
  }
  const text = String(objective || "").trim();
  if (!text) return { ok: false, reason: "empty objective" };

  // `sourceConductorDispatchFeed` returns the DISPLAY WRAPPER `{ok, feed, error}`, never the feed
  // itself — its own contract says so, and `sourceConductorDispatch()` above unwraps it correctly
  // (`conductorDispatch.ok`, `conductorDispatch.feed.dispatched`). This path did not: it bound the
  // wrapper to a variable named `feed` and then read `feed.dispatched` and `feed.reason` off it.
  // Both are undefined on a wrapper, so the guard was ALWAYS taken and the reason was ALWAYS the
  // fallback string — meaning runObjective could never dispatch, for any objective, on any host,
  // since EPC-03 joined the loop. Measured on the operator's host 2026-09-05: the emitter run by
  // hand with the same objective returns `dispatched: true` with two assignments, while the app
  // reported "the governed dispatch did not run" from this line.
  let src;
  try {
    src = await sourceConductorDispatchFeed({ cwd: REPO_ROOT, objective: text });
  } catch (e) {
    log(`objective: governed dispatch unavailable (fail-closed, nothing delegated): ${e.message}`);
    return { ok: false, reason: `dispatch unavailable: ${e.message}`, delegations: [] };
  }
  const feed = src && src.feed;
  if (!src || src.ok !== true) {
    // The emitter could not be reached or parsed. Its own error is the honest reason; the
    // unavailable feed rides along so callers still have a shape to fold.
    const why = (src && src.error) || "the conductor dispatch feed could not be sourced";
    log(`objective: dispatch feed unavailable (fail-closed): ${why}`);
    return { ok: false, reason: why, feed: feed || null, delegations: [] };
  }
  if (!feed || feed.dispatched !== true) {
    // A governed NON-dispatch: the emitter ran and declined, e.g. a plan-gate block. Surfaced as
    // its own reason, never as a fabricated dispatch.
    const why = (feed && feed.reason) || "the governed dispatch did not run";
    log(`objective: not dispatched (fail-closed): ${why}`);
    return { ok: false, reason: why, feed, delegations: [] };
  }

  // Only assignments naming a pane that is actually up. An assignment to an id with no live pane
  // is reported rather than written into whatever pane happens to be nearest.
  // `nodeId`, NOT `node_id`. A worker record is minted by `worker-spawn.emptyRecord` in camelCase
  // (`nodeId: identity.node_id` — the snake_case name belongs to the Python identity payload, not
  // to the record built from it), and every other reader in this codebase gets it right:
  // `application-control.deliverableNodeIds` and `operational-state.operationalNodeStatus` both
  // read `rec.nodeId`. This line alone read the Python spelling, so the lookup was undefined on
  // every record, the map was always empty, and EVERY assignment reported "no live pane is
  // registered for this assignment" — including for panes the same log had just recorded as LIVE
  // under exactly that node id. Measured on the operator's host 2026-09-05: dispatch produced two
  // assignments to worker-pane-2/worker-pane-3 while worker-pane-2 was live in this very session.
  const objectiveId = require("node:crypto").randomUUID();
  const registered = workerLauncherInstance ? workerLauncher().records() : [];
  const selected = selectObjectiveRecipients(liveWorkerRecords(), registered, text);
  try {
    await runtimeJournal().record({
      node_id: "conductor", pane_id: "conductor", model: "(plan)",
      status: "conductor_reasoning", prompt: text, task_id: objectiveId, objective: text,
      answer: "plan recorded as conductor reasoning; recipients are live worker panes",
      reason: "plan is the conductor's reasoning record; it does not select recipients",
      self_published: false, source: "observed_pane_output",
    });
  } catch { /* journal absence is reported on the worker turns */ }

  const delegations = selected.skipped.map((row) => ({ ...row, objective_id: objectiveId, task_id: objectiveId }));
  for (const rec of selected.recipients) {
    const result = await delegateToWorkerPane(rec.pane_id, rec.node_id, {
      task_id: objectiveId,
      objective: text,
      expected_output: "a concise, complete answer",
    }, options);
    delegations.push({ ...result, objective_id: objectiveId, pane_number: rec.pane_number });
    log(`objective: ${rec.node_id} (${rec.pane_id}) delivered=${result.delivered} answered=${result.answered}`
      + (result.reason ? ` — ${result.reason}` : ""));
  }

  return {
    ok: true,
    objective: text,
    objective_id: objectiveId,
    assigned: selected.recipients.length,
    answered: delegations.filter((d) => d.answered).length,
    // Carried verbatim so a caller cannot mistake this for an acceptance: the legs are the feed's.
    legs: feed.legs,
    live_workers_owed: feed.live_workers_owed,
    delegations,
    feed,
  };
}

ipcMain.handle("conductor:run-objective", async (_e, payload) => {
  const p = payload && typeof payload === "object" ? payload : {};
  return runObjective(p.objective, p.options || {});
});

/** Why a system write into this pane would be refused right now, or null. Callers that own an
 *  operational state consult this so a withheld write is reported as the provider state it is. */
function paneWriteRefusalFor(paneId) {
  return paneWriter.refusalFor(paneId);
}

function setWorkerOperationalState(paneId, operationalState, patch = {}) {
  const record = workerLauncher().updateRecord(paneId, { operationalState, ...patch });
  const chrome = { ...(paneChrome.get(paneId) || record.chrome || {}), node_state: operationalState };
  paneChrome.set(paneId, chrome);
  if (win && !win.isDestroyed()) win.webContents.send("pane:chrome", paneId, chrome);
  pushState();
  pushConductor();
  return record;
}

/** The structured failure the DEADLINE paths report (`worker_task_soft/hard_deadline`). Readiness
 *  builds its own inside `control/worker-readiness.js` from the same helper — a deadline is a
 *  different subsystem and keeps its own call site. */
function readinessFailure(record, stage, terminalState = "STALLED") {
  const operations = sovereignControl ? sovereignControl.operationState(record.nodeId) : { last: null };
  return structuredProviderFailure({
    provider: record.chrome && record.chrome.provider,
    model: record.chrome && record.chrome.model_slug,
    nodeId: record.nodeId, stage,
    lastSuccessfulMcpOperation: operations.last && operations.last.ok ? operations.last.operation
      : record.lastSuccessfulMcpOperation,
    lastProgressTimestamp: record.lastProgressAt,
    providerTerminalState: terminalState,
    leaseState: record.leaseId ? "active" : "not_applicable",
    processState: record.state,
  });
}

// U329 (unit 19.4): the readiness state machine itself lives in `control/worker-readiness.js`. What
// stays here is the binding — the real launch record, the real MCP connection/operation state, the
// real gated write path, and the bounded window over the real ring buffer. Nothing in this file
// decides an order any more, which is the point: the order WAS the defect (a screen scrape ran
// before the connection check and could not be tested from here).
const workerReadiness = createWorkerReadiness({
  now: () => Date.now(),
  sleep: pause,
  window: readinessWindow,
  record: (paneId) => workerLauncher().record(paneId),
  processIdentity: (paneId) => (manager ? manager.processIdentity(paneId) : null),
  setOperationalState: (paneId, state, patch) => setWorkerOperationalState(paneId, state, patch),
  mcpState: (nodeId) => (sovereignControl
    ? sovereignControl.connectionState(nodeId) : { state: "disconnected" }),
  operationCount: (nodeId, operation) => (sovereignControl
    ? sovereignControl.operationCount(nodeId, operation) : 0),
  operationState: (nodeId) => (sovereignControl
    ? sovereignControl.operationState(nodeId) : { last: null }),
  writeRefusal: (paneId) => paneWriteRefusalFor(paneId),
  writePrompt: (paneId, prompt) => writePanePrompt(paneId, prompt),
  mcpTimeoutMs: () => MCP_READINESS_TIMEOUT_MS,
  responseDeadlineMs: () => PEER_RESPONSE_DEADLINE_MS,
  log,
});

const runWorkerReadiness = (paneId) => workerReadiness.run(paneId);

const runConductorReadiness = createConductorReadiness({
  descriptor: conductorDescriptor,
  launch: () => conductorLaunch,
  setLaunch: (next) => { conductorLaunch = next; },
  push: pushConductor,
  admit: conductorAdmission,
  waitForNodeMcp,
  mcpTimeoutMs: () => MCP_READINESS_TIMEOUT_MS,
  operationCount: (nodeId, operation) => (sovereignControl
    ? sovereignControl.operationCount(nodeId, operation) : 0),
  buildProbe: buildRoundTripProbe,
  window: readinessWindow,
  paneId: () => conductorPaneId,
  writeRefusal: paneWriteRefusalFor,
  writePrompt: writePanePrompt,
  responseDeadlineMs: () => PEER_RESPONSE_DEADLINE_MS,
  now: () => Date.now(),
  sleep: pause,
  answerObserved,
  processIdentity: (paneId) => (manager ? manager.processIdentity(paneId) : null),
  mcpState: (nodeId) => (sovereignControl ? sovereignControl.connectionState(nodeId) : null),
  observedEvidence: observedReadinessEvidence,
});

const applicationControl = createApplicationControl({
  repoRoot: REPO_ROOT,
  workerTaskSoftDeadlineMs: WORKER_TASK_SOFT_DEADLINE_MS,
  workerTaskHardDeadlineMs: WORKER_TASK_HARD_DEADLINE_MS,
  peerResponseDeadlineMs: PEER_RESPONSE_DEADLINE_MS,
  debateTurnDeadlineMs: DEBATE_TURN_DEADLINE_MS,
  workerRecordFor, readinessFailure, setWorkerOperationalState, notifyNode,
  conductorNodeId: () => conductorLaunch.nodeId,
  updateWorkerRecord: (paneId, patch) => workerLauncher().updateRecord(paneId, patch),
  pushConductor, fetchPickerModel,
  setPickerModel: (model) => { lastPickerModel = model; },
  pickerModel: () => lastPickerModel,
  liveWorkerRecords, operationalNodeStatus, runWorkerReadiness,
  spawnFromSelection,
  workerRecordForPane: (paneId) => workerLauncher().record(paneId),
  chromeFor: (paneId) => paneChrome.get(paneId),
  setChrome: (paneId, chrome) => paneChrome.set(paneId, chrome),
  persistLayoutSnapshot,
  sendPaneChrome: (paneId, chrome) => {
    if (win && !win.isDestroyed()) win.webContents.send("pane:chrome", paneId, chrome);
  },
  killPane: (paneId) => manager.kill(paneId),
  assignmentRefusal,
  mcpState: (nodeId, record) => (sovereignControl && record
    ? sovereignControl.connectionState(nodeId) : null),
  writePanePrompt, log,
  // EPC-03 L5-3/L5-4. Reachable from the control surface so the delegation loop is WIRED rather
  // than merely built; nothing here calls it on launch, because an app launch must not start
  // spending model time on the operator's behalf.
  delegateToWorkerPane,
});
const {
  list_models: controlListModels,
  spawn_worker: controlSpawnWorker,
  stop_worker: controlStopWorker,
  preflight_assignment: controlPreflightAssignment,
  assign_task: controlAssignTask,
  get_worker_status: controlGetWorkerStatus,
  notify_message: controlNotifyMessage,
  notify_debate: controlNotifyDebate,
  notify_debate_turn: controlNotifyDebateTurn,
} = applicationControl.handlers;
const onSovereignOperation = (identity, event) => applicationControl.deadlines.onOperation(identity, event);
const clearNodeDeadlines = (nodeId) => applicationControl.deadlines.clearNodeDeadlines(nodeId);

async function ensureSovereignControl() {
  if (sovereignControl) return sovereignControl;
  sovereignControl = new SovereignControlServer({ log, onOperation: onSovereignOperation, handlers: {
    list_models: controlListModels, spawn_worker: controlSpawnWorker, stop_worker: controlStopWorker,
    preflight_assignment: controlPreflightAssignment,
    assign_task: controlAssignTask, get_worker_status: controlGetWorkerStatus,
    notify_message: controlNotifyMessage, notify_debate: controlNotifyDebate,
    notify_debate_turn: controlNotifyDebateTurn,
  } });
  await sovereignControl.start();
  log(`control: Sovereign MCP application gateway listening on 127.0.0.1:${sovereignControl.port}`);
  return sovereignControl;
}

// ---- bootstrap ---------------------------------------------------------------
async function bootstrap() {
  const gw = await resolveGateway();
  log(`gateway ${gw.spawned ? "spawned" : "from env"} on 127.0.0.1:${gw.port}`);
  const client = new IpcClient({ host: "127.0.0.1", port: gw.port, nodeId: NODE_ID, token: gw.token, key: gw.key });
  // A SEPARATE read channel for the inspector, on the same loopback credential. The IpcClient
  // control channel is strictly sequential (one request in flight); the supervisor already owns
  // `client` for its 5 s health heartbeat + session_event notifies, so the inspector's 8-status
  // sweep gets its own connection rather than contending with (and being refused by) the
  // heartbeat. The gateway is threaded and authenticates per-connection, so a second channel for
  // the same node identity is legitimate. It connects lazily on the first inspector:fetch.
  ipcClient = new IpcClient({ host: "127.0.0.1", port: gw.port, nodeId: NODE_ID, token: gw.token, key: gw.key });
  // NOTE (Phase 16D `.statusbar`): the status bar no longer rides a dedicated IPC channel — the
  // shell's EchoControlSurface gateway does not expose subscription_status, so the count is sourced
  // from the real governor via the bounded emitter (statusbar:fetch → governor-source). The IPC
  // surface (SubscriptionStatusControlSurface) remains the design endpoint for a live governor-backed
  // gateway at 16F; statusbar/source.js + its test stay as that endpoint's proven data path.
  supervisor = new IpcSupervisor({
    client,
    // loss edge: fail closed — tear every session down, no naked session survives the gap.
    onSupervisionLost: () => { if (manager) manager.killAll(); pushState(); },
    // restore edge: the channel re-verified on a new epoch — the UI recovers (re-push chrome +
    // recompute the §10.2 layout). Re-admission of new sessions is now open again.
    onSupervisionRestored: () => { pushState(); emitLayoutNow(); },
    log,
  });
  manager = new SessionManager({ ptyFactory, supervisor });
  manager.onEvent((event) => {
    if (event.kind === "data") {
      // Tag every chunk with a per-session seq (registry.feed already ran in the session-manager
      // before this emit, so the scrollback snapshot and this seq stay in lockstep). The renderer
      // buffers live chunks until it has replayed scrollback, then drops chunks <= the snapshot
      // boundary — closing the blank-pane defect (banner printed before the term view existed).
      const seq = (dataSeq.get(event.id) || 0) + 1;
      dataSeq.set(event.id, seq);
      if (win && !win.isDestroyed()) win.webContents.send("pane:data", event.id, event.data.toString("utf8"), seq);
    }
    // Phase 17A `.pty`: the live conductor session ending (its own exit, an operator close, or the
    // fail-closed killAll on supervision loss) hands the durable I-X3 terminal back — D-LOOP-1, and
    // the operator's own subscription is not held by a session that no longer exists.
    if (event.kind === "exit" || event.kind === "kill") {
      trackSessionRelease(onConductorSessionEnded(event), "conductor");
      const endedWorker = workerLauncher().record(event.id);
      if (endedWorker && endedWorker.nodeId) clearNodeDeadlines(endedWorker.nodeId);
      // Phase 17B `.spawn` / D-LOOP-1: the same rule for a governed WORKER pane — a frontier worker
      // session that ended must not keep holding 1 of the operator's 2 durable terminals. A local
      // worker holds none and the release reclaims nothing; it is called anyway so the lifecycle has
      // one shape. Never throws into the event loop.
      trackSessionRelease(workerLauncher().onWorkerSessionEnded(event), "worker");
      // …and the pane's CHROME has to stop claiming a running governed node the moment there is not
      // one. It was written once, at launch, and never revised: after an ordinary exit — or after
      // the fail-closed `killAll` on supervision loss, i.e. exactly when supervision is GONE —
      // `paneMeta()` still reported `node_state:"running", governed:true`, and every later layout
      // snapshot baked that into the state a restart replays (spec-audit MAJOR-1, invariants 3/27).
      markWorkerPaneChromeEnded(event);
    }
    // persist the append-only lifecycle log on every state-changing event so a full shell
    // restart can reconstruct what existed (best-effort; a write failure never breaks a session).
    if (["spawn", "exit", "kill", "refused"].includes(event.kind)) {
      recoveryStore.persist(manager.registry.eventLog());
      persistLayoutSnapshot(); // keep the layout snapshot in step with the session log for recovery
      pushState();
    }
  });

  // Cross-restart reconstruction: fold the persisted layout snapshot + the session view + the
  // current admission state into the conductor-first layout the shell rebuilds (§15E .recovery /
  // OP-7 §12.4). Fail-closed — the pinned CONDUCTOR is always pane 1; interrupted worker panes are
  // surfaced for SUPERVISED relaunch, NEVER auto-respawned (invariant 2); nothing is admitted until
  // the channel re-verifies. The actual pane-1 CONDUCTOR is (re)placed by createConductorPane() on
  // did-finish-load; this payload gives the renderer the recovered structure to draw.
  const recovered = reconstructConductorFirstLayout();
  const interrupted = recovered.interrupted;
  if (interrupted.length) {
    log(`recovery: ${interrupted.length} interrupted pane(s)/session(s) from a prior run — supervised relaunch required (no naked re-spawn)`);
  }
  log(`recovery: conductor-first layout reconstructed — CONDUCTOR pane 1 + ${recovered.summary.workers} worker pane(s), ${interrupted.length} needing relaunch, admission ${recovered.admissionOpen ? "OPEN" : "SHUT (awaiting channel)"}`);
  if (win && !win.isDestroyed()) win.webContents.send("shell:recovery", { layout: recovered, interrupted: recoveryStore.loadInterrupted() });

  const ready = await supervisor.start();
  log(ready ? "supervision READY (verified control-plane channel)" : "supervision NOT ready — sessions refused until the channel verifies");
  await ensureSovereignControl();
}

/**
 * The operator's keyboard, as ELECTRON MAIN sees it (`before-input-event` fires before the page does).
 *
 * Two gestures, and the second is the one that matters (Phase 17C `.disarm`, U166). The explicit
 * Ctrl+Shift+Escape chord was the ONLY way an admitted voice turn ever ended, and it appears in no
 * chrome, no string and no operator document — so in practice the first spoken utterance of a session
 * muted the operator's own typing until the session was killed. Ordinary typing now ends the turn:
 * everything the CLI does between an admitted spoken prompt and the operator's next keystroke is
 * treated as voice-originated and non-executing, and the operator taking the keyboard back is the
 * bound. The chord remains for ending it WITHOUT typing into the pane.
 *
 * Only the chord is consumed; an ordinary keystroke must still reach the pane the operator is typing
 * into — main disarms first and the character goes on to the CLI, in that order, so the prompt it
 * begins is admitted rather than blocked.
 */
function handleOperatorResumeInput(event, input) {
  if (shouldOperatorResumeVoiceTurn(input)) {
    event.preventDefault(); // this authority gesture is consumed by main, never typed into the CLI
    conductorVoiceAuthority.disarm("electron_main_operator_chord", { chord: "Ctrl+Shift+Escape" });
    return true;
  }
  if (isOperatorTypedKey(input)) {
    // `key_kind` only — an append-only audit that reached evidence receipts and recorded WHICH keys
    // the operator pressed would be a keylogger, which no invariant asks for.
    const kind = operatorKeyKind(input);
    conductorVoiceAuthority.disarm("electron_main_before_input_event", { key_kind: kind });
    // W-39: the residue block lifts HERE, on the OS input path, and nowhere else. The operator
    // taking the input line back is what resolves it — whatever an unsubmitted voice utterance left
    // there is now theirs to see and edit. Gated on the two RESOLVING kinds (Enter, or a Ctrl/Alt/
    // Meta chord such as Ctrl-C): clearing on any operator key would discard the block the moment a
    // single character was typed, which is the same defect with a different trigger.
    //
    // The existing `operatorKeyKind` classification carries it. No new provenance flag, and
    // `operatorInputResolvesResidue` is untouched — that predicate was always correct; it was being
    // asked from a channel the child can reach.
    if (kind === "submit" || kind === "control-combination") {
      clearConductorInputResidue("the operator submitted or cancelled the conductor input");
    }
  }
  return false;
}

/**
 * W-30: the ONE navigation this shell ever performs is its own `loadFile`. Everything else is an
 * escape. `file://` is the permitted set, which is the review's recommended shape — and its limit is
 * recorded rather than described away: a navigation to some OTHER local file is still permitted. The
 * renderer stays sandboxed with `contextIsolation`, so the value of that to an attacker is low, and
 * the advisory class being closed here is escape to REMOTE content.
 */
const navigationIsPermitted = (url) => String(url || "").startsWith("file://");

function makeWindow() {
  win = new BrowserWindow({
    width: 1600, height: 950, title: "Sovereign Orchestration Workspace",
    backgroundColor: "#0b0e14",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  // The child owns the hook bearer and the renderer is least-trusted, so neither may end a voice
  // turn. Only what Electron main observes on the OS input path is operator-authenticated: the
  // operator's ORDINARY typing (17C `.disarm`/U166 — this is what gives the restriction an end, and
  // it is not scoped to the conductor pane; see U170) or the explicit Ctrl+Shift+Escape chord, which
  // ends it without typing anything into the CLI.
  win.webContents.on("before-input-event", (event, input) => {
    handleOperatorResumeInput(event, input);
  });
  // Under SHELL_SELFCHECK, pass a load-time query flag so the renderer arms its read-only
  // self-check observability hook ONLY for the diagnostic run — it is absent in a normal operator
  // launch (defense-in-depth; the hook grants no authority regardless).
  // Phase 17C `.mic`: the renderer needs the MICROPHONE for push-to-talk — and nothing else at all.
  // Electron's default is to grant every permission a page asks for; the renderer is the least-trusted
  // surface (invariant 29) and this shell renders untrusted PTY output into its DOM, so the default is
  // replaced by an explicit allow-list.
  //
  // The allow-list is of one CAPABILITY, not one string. Electron's `media` permission covers audio AND
  // video, discriminated by `details.mediaTypes` — granting it wholesale would hand the sandbox the
  // operator's webcam, which no invariant asks for and which the STT-only scope (invariant 24) excludes.
  // A `media` request that mentions video is refused outright rather than partially satisfied.
  // GRANTS are logged as well as denials: a capability the operator cannot see being taken is not
  // observable state (invariant 27).
  const allowMedia = (permission, details) => {
    if (permission !== "media" && permission !== "audioCapture") return false;
    const types = (details && details.mediaTypes) || null;
    if (Array.isArray(types) && types.length) return types.every((t) => t === "audio");
    return permission === "audioCapture";   // no declared types ⇒ only the unambiguous audio permission
  };
  const decide = (permission, details) => {
    const granted = allowMedia(permission, details);
    log(`renderer permission ${granted ? "GRANTED" : "DENIED"}: ${permission}`
      + `${details && details.mediaTypes ? ` [${details.mediaTypes.join(",")}]` : ""}`);
    return granted;
  };
  win.webContents.session.setPermissionRequestHandler((_wc, permission, callback, details) => callback(decide(permission, details)));
  // The synchronous check path (`navigator.permissions.query`, device-label enumeration) has its own
  // handler and otherwise falls back to Electron's permissive default — the same rule applies to both.
  win.webContents.session.setPermissionCheckHandler((_wc, permission, _origin, details) => allowMedia(permission, details));
  // W-30, the two escapes Electron leaves open by default (R-04: NEITHER was present).
  // `window.open` is denied outright — there is no browsing surface in this app (zero occurrences
  // repo-wide) so an allow-list would be inventing one. `will-navigate` is the top-level half: the
  // CSP is `script-src 'self'` and `default-src` does NOT constrain navigation, so without this the
  // renderer can navigate the window to remote content and nothing stops it.
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  win.webContents.on("will-navigate", (event, url) => {
    if (navigationIsPermitted(url)) return;
    event.preventDefault();
    // Invariant 27: a refusal must be visible. The SCHEME only — a URL from a compromised renderer
    // is attacker-chosen text and may carry a token in its query string, and §2.2's rule is that we
    // log names, never values.
    const scheme = (/^[a-z][a-z0-9+.-]*:/i.exec(String(url || "")) || ["(no scheme)"])[0];
    log(`renderer navigation DENIED: ${scheme}`);
  });
  win.loadFile(path.join(__dirname, "renderer", "index.html"),
    process.env.SHELL_SELFCHECK ? { query: { selfcheck: "1" } } : undefined);
  if (process.env.SHELL_SELFCHECK) {
    // surface renderer console + crashes to the inherited stdout so the self-check is diagnosable
    // only warnings/errors (level >= 2) — logging info/log would feed back through S.onLog → console.log
    win.webContents.on("console-message", (_e, level, message, line, sourceId) => {
      if (level >= 2) log(`[renderer:${level}] ${message} (${sourceId}:${line})`);
    });
    win.webContents.on("render-process-gone", (_e, details) => log(`[renderer] gone: ${JSON.stringify(details)}`));
    win.webContents.on("did-fail-load", (_e, code, desc) => log(`[renderer] did-fail-load ${code} ${desc}`));
  }
  // Debounced relayout channel (Plan §10.2): onLayout sends the plan the renderer reflows to.
  layoutSched = new LayoutScheduler({ onLayout: (plan) => { if (win && !win.isDestroyed()) win.webContents.send("shell:layout", plan); } });
  win.webContents.on("did-finish-load", () => {
    createConductorPane(); // conductor-first: pane 1 is the pinned CONDUCTOR node (§12.4)
    // A recovery snapshot may already hold worker pane-N ids. New ids must resume above that
    // high-water mark, while the structural conductor remains the first pane minted this boot.
    paneSeq = Math.max(paneSeq, resumePaneSeq({ snapshot: recoveryStore.loadLayout(), paneSeq }));
    pushState();
    pushApprovals();       // seed the badge from the cached model immediately (honest 0 until sourced)
    // Phase 17D `.events`: start THIS run's approval log empty. A pending row names a broker
    // classification and a session that do not survive the process, so carrying yesterday's rows into
    // today's drawer would re-create finding F2 one restart later. What the operator sees at launch is
    // what this run has produced: nothing, yet.
    // ONCE per process, not once per `did-finish-load`: this handler also fires on a renderer reload,
    // and truncating there would silently discard approvals the operator had pending in a session that
    // never ended. The window reloading is not the session restarting.
    if (!sessionApprovalsStarted) { sessionApprovalsStarted = true; sessionApprovals.begin(); }
    // Source the drawer from that log in the background (a `py -3.12` start must not sit on first
    // paint), then re-push the badge. Fail-closed + bounded.
    refreshApprovalModel().then(() => pushApprovals()).catch((e) => log(`approvals: initial source failed (fail-closed empty drawer): ${e && e.message}`));
    // Phase 17C `.probe` (U74): start the STT-engine probe in the BACKGROUND at first paint. It costs
    // 7–18 s on this host (measured) and is allowed up to 90 s, so it must never sit on the paint path
    // — until it answers the chrome honestly reads "probing…". When it lands, push the state so the
    // badge flips itself with no operator action. `.start()` never rejects (faults settle as
    // `unavailable` with the reason named), but the catch stays: a background task must not be able to
    // raise an unhandled rejection in the shell.
    ensureVoiceProbe().start()
      .then((s) => { log(`voice: STT engine probe → ${s.state} (${s.elapsedMs}ms) — ${s.reason}`); pushVoice(); })
      .catch((e) => log(`voice: STT engine probe failed unexpectedly: ${e && e.message}`));
    // Phase 17C `.mic` / invariant 26: construct the capture store AT STARTUP so its purge actually
    // runs at startup. Built lazily on first capture, the "startup purge" only ran when the operator
    // next used voice — so recorded speech orphaned by a crash could survive weeks of sessions in
    // which they never pressed talk, while the code claimed a one-session bound.
    try { ensureCaptureStore(); } catch (e) { log(`voice: capture store unavailable: ${e && e.message}`); }
    emitLayoutNow();
    if (rendererReadyResolve) rendererReadyResolve(); // release the self-check gate
  });
}

function teardown() {
  // Do not reset/stop voice authority here: before-quit is a kill REQUEST, not proof that the
  // conductor PTY is gone. SessionManager's onExit path resets it when confirmed; if Electron exits
  // first, loss of this authenticated loopback service is fail-closed in the child hook.
  // Phase 17C `.probe` / D-LOOP-1: abandon an in-flight STT probe. It runs 7–22 s on this host (up to
  // its 90 s budget), so quitting inside that window would otherwise orphan the emitter.
  try { if (voiceProbe) voiceProbe.dispose(); } catch { /* teardown must never throw */ }
  // Phase 17C `.mic` / invariant 26: leave no recorded speech behind. `withCapture` already deletes on
  // every normal path; this catches a quit that raced an in-flight transcription.
  try { if (captureStore) captureStore.purgeOwned(); } catch { /* teardown must never throw */ }
  try { if (stopCaptureJanitor) stopCaptureJanitor(); } catch { /* teardown must never throw */ }
  // Signal every PTY before considering any lease release. The synchronous kill event moves the
  // conductor to `terminating`; only node-pty's later onExit can clear authority and release its
  // durable terminal. If Electron exits first, dead-holder reaping observes the vanished owner.
  try { manager && manager.killAll(); } catch { /* ignore */ }
  // Never release an I-X3 terminal on quit intent. If node-pty confirms exit before Electron leaves,
  // the normal exact-generation callback releases it; otherwise the durable ledger reaps this holder
  // only after the Electron process itself is actually gone.
  // U334 (unit 19.7): the authenticated gateway is torn down HERE, with every other resource, and no
  // longer only as a bare `await` two functions later. `stop()` is bounded and idempotent, so
  // starting it at kill-request time revokes every node credential immediately while the quit path's
  // `await` still receives the same outcome. Fire-and-forget on purpose: teardown() is synchronous
  // and must never throw — the awaiting caller is where the result is read.
  try { if (sovereignControl) sovereignControl.stop().catch(() => {}); } catch { /* teardown must never throw */ }
  try { layoutSched && layoutSched.dispose(); } catch { /* ignore */ }
  try { ipcClient && ipcClient.close(); } catch { /* ignore */ }
  try { supervisor && supervisor.stop(); } catch { /* ignore */ }
  try { gatewayProc && gatewayProc.kill(); } catch { /* ignore */ }
}

function waitForChildExit(proc, timeoutMs = 15000) {
  if (!proc || proc.exitCode !== null || proc.signalCode !== null) return Promise.resolve(true);
  return new Promise((resolve) => {
    let settled = false;
    const finish = (exited) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      proc.off("exit", onExit);
      resolve(exited);
    };
    const onExit = () => finish(true);
    const timer = setTimeout(() => finish(false), timeoutMs);
    proc.once("exit", onExit);
  });
}

async function teardownSelfCheck() {
  teardown();
  const sessions = manager
    ? await manager.shutdown(15000)
    : { complete: true, pending: [] };
  const releases = await waitForSessionReleases(15000);
  const heldWorkers = workerLauncher().heldSessions();
  const conductorHeld = conductorLaunch.leaseId ? [conductorLaunch.sessionId] : [];
  let voiceStop = null;
  if (sessions.complete && releases.complete && heldWorkers.length === 0 && conductorHeld.length === 0) {
    voiceStop = await conductorVoiceAuthority.stop();
  }
  // teardown() above already started this; the memoised promise is what returns here (U334).
  const controlStop = sovereignControl ? await sovereignControl.stop() : null;
  const gatewayExited = await waitForChildExit(gatewayProc);
  const controlComplete = !controlStop || controlStop.closed === true;
  const voiceComplete = !voiceStop || voiceStop.closed === true;
  return {
    complete: sessions.complete && releases.complete && heldWorkers.length === 0
      && conductorHeld.length === 0 && gatewayExited && controlComplete && voiceComplete,
    sessions, releases, heldWorkers, conductorHeld, gatewayExited, controlStop, voiceStop,
  };
}

let normalQuitStarted = false;
async function completeNormalQuit(faultKind = null) {
  // SW-CONDUCTOR-001 Phase 3: stop the conductor bridge before the sessions it writes to are
  // torn down — explicitly, not relying on the kill events to deliver onConductorSessionEnded
  // on a quit or fault path.
  detachConductorBridge("the shell is quitting");
  teardown();
  const sessions = manager
    ? await manager.shutdown(15000)
    : { complete: true, pending: [] };
  // SessionManager waits for node-pty exits, while the durable lease/node closures are asynchronous
  // listeners of those exits. Do not let Electron exit until those exact-generation callbacks finish.
  const releases = await waitForSessionReleases(15000);
  const heldWorkers = workerLauncher().heldSessions();
  const conductorHeld = conductorLaunch.leaseId ? [conductorLaunch.sessionId] : [];
  const terminalsReleased = releases.complete && heldWorkers.length === 0 && conductorHeld.length === 0;
  const voiceStop = sessions.complete && terminalsReleased
    ? await conductorVoiceAuthority.stop() : null;
  // U334: bounded, and started by teardown() above — this await cannot outlive the gateway's budget.
  const controlStop = sovereignControl ? await sovereignControl.stop() : null;
  const gatewayExited = await waitForChildExit(gatewayProc);
  const controlComplete = !controlStop || controlStop.closed === true;
  const voiceComplete = !voiceStop || voiceStop.closed === true;
  const complete = sessions.complete && terminalsReleased && gatewayExited
    && controlComplete && voiceComplete;
  if (!complete) {
    log(`normal teardown incomplete: sessions=${JSON.stringify(sessions.pending)}, `
      + `pendingReleases=${releases.pending}, heldWorkers=${JSON.stringify(heldWorkers)}, `
      + `conductorHeld=${JSON.stringify(conductorHeld)}, gatewayExited=${gatewayExited}, `
      + `controlStop=${JSON.stringify(controlStop)}, voiceStop=${JSON.stringify(voiceStop)}`);
  } else {
    log("normal teardown complete: zero managed terminal sessions; gateway exited"
      // The control gateway's own outcome is stated even on the happy path: a stop that had to
      // destroy connections, or that outlived its budget, is not a silent detail of a clean quit.
      + `${controlStop && controlStop.was_listening
        ? `; control gateway ${controlStop.closed ? "closed" : "TIMED OUT"}`
          + `${controlStop.forced ? " (connections destroyed)" : ""} in ${controlStop.waited_ms} ms`
        : ""}`);
  }
  await mainProcessLogger.flushAndDetach();
  // W-18a: a teardown reached through a process FAULT never reports success, however
  // clean the release was -- the process is dying from an unhandled fault, and exit 0
  // would tell the launcher the opposite.
  app.exit(faultKind || !complete ? 1 : 0);
}

app.whenReady().then(async () => {
  registerIpc();
  // Source the authoritative CONDUCTOR selection BEFORE the window renders pane 1 (U65), so the badge
  // is drawn from Python from the first paint. Bounded + fail-closed, so it can never wedge startup.
  await sourceConductorFeed();
  // Phase 16C `.spawn`: source the governed spawn of pane 1 (spawn_conductor_pane, full live-gate
  // chain, I-X3 counted-then-released — D-LOOP-1) BEFORE the window renders, so pane 1's node_state is
  // governed-born from the first paint. Bounded + fail-closed — a fault leaves an honest placeholder.
  await sourceConductorSpawn();
  makeWindow();
  // F-130. Remember whether the governed core actually came up. The live-ready receipt below must
  // reflect this, not be written {ok:true} unconditionally: a caught bootstrap failure (or a
  // bootstrap that resolves while supervisor.start() returns not-ready) used to still publish
  // {ok:true}, so the shell showed "Multi-Model Terminal: READY" for an instance whose every pane
  // spawn is refused.
  let bootstrapError = null;
  try {
    await bootstrap();
  } catch (e) {
    bootstrapError = (e && e.message) || String(e);
    log(`bootstrap failed (fail-closed, no sessions will spawn): ${bootstrapError}`);
  }
  // Phase 16C `.dispatch`: source the govern-born conductor's governed DISPATCH AFTER the window is up
  // (it spins a bounded loopback MCP flow, mock-first — heavier than a plain read, so it must not delay
  // first paint). Bounded + fail-closed — a fault leaves an honest "dispatch unavailable". Then push the
  // refreshed conductor state so the dispatch line renders.
  await sourceConductorDispatch();

  // CP-M1 G15: live-boot readiness receipt for the shell's receipt_file probe.
  // Normal start path only - under SHELL_SELFCHECK the selfcheck flow writes its own
  // PHASE16A_SELFCHECK.json instead (paths stay distinct by design). A failure here writes
  // nothing, so the shell probe times out and reports FAILED(TIMEOUT) honestly.
  if (!process.env.SHELL_SELFCHECK) {
    try {
      const fs = require("fs");
      // LOCAL-01 F-6 (OD-34 / N-29). This receipt is written on EVERY normal launch, so writing
      // it into the git-tracked `docs/evidence/receipts` meant that simply USING the product
      // dirtied the release candidate — and it is what made this run's own BOOT find a dirty
      // tree, as FIXUP-01's did before it. That was fixed by moving it to a gitignored
      // `.runtime/` lane INSIDE the installation.
      //
      // SWS-CORRECTIVE-01 C3. Inside the installation was still the wrong place. Two things
      // were wrong with it: `shell/modules/sow.json` declared `${state_root}/.recovery` and
      // `${state_root}/receipts` and nothing else, so the write every normal launch performs
      // was declared nowhere; and a normal launch therefore could not survive a non-writable
      // installation directory, which a per-machine install under Program Files is.
      //
      // The receipt now goes to this module's state root, which is the agreed writable
      // location and the one the adapter declares. `SOVEREIGN_WORKSPACE_STATE` is set for
      // every module by `shell/src/adapter.py` whether or not its adapter names it, so under
      // the shell this is always defined. The fallback mirrors `workspace_state_root()` in
      // that file rather than reaching back into the installation, so a developer running the
      // app directly also writes outside the install tree.
      const receiptDir = path.join(sowStateRoot(), "receipts");
      fs.mkdirSync(receiptDir, { recursive: true });
      // F-130. `ok` is the TRUTH about the governed core: bootstrap resolved AND the supervisor is
      // ready. A failed core writes {ok:false, reason} so the shell's receipt probe fails fast and
      // reports the module unhealthy, instead of a green {ok:true} over an instance that refuses
      // every spawn. The adapter now requires {ok:true, supervised:true} (shell/modules/sow.json).
      const supervised = Boolean(supervisor && supervisor.ready);
      const ready = bootstrapError === null && supervised;
      fs.writeFileSync(path.join(receiptDir, "SHELL-LIVE-READY.json"),
        JSON.stringify({
          ok: ready,
          supervised: supervised,
          reason: ready ? null : (bootstrapError || "supervisor not ready"),
          pid: process.pid,
          bootedAt: new Date().toISOString(),
        }, null, 2));
    } catch (e) {
      log("shell-live receipt write failed (probe will report TIMEOUT honestly): " + (e && e.message));
    }
  }
  pushConductor();
  // Phase 17A `.pty` — CONDUCTOR-FIRST, LIVE (directive §16 track 17A / OP-8 §13.1): pane 1 runs the
  // real interactive `claude` session on launch, so the operator lands in a conductor chat rather
  // than a black pane. It is attempted only after supervision has had its chance to verify (the spawn
  // itself re-checks and fails closed), it consumes exactly one governed I-X3 terminal, and it is
  // skipped during a self-check run (which drives the launch explicitly) or when the operator sets
  // SOW_CONDUCTOR_AUTOLAUNCH=0. A failure here never wedges startup — the pane stays honestly dark.
  // OPTION C, ruled by the operator (ENTRY 017 / OD-32): the Conductor "launches, accepts the
  // operator's typing, and spawns nothing until he selects a model and sends something."
  //
  // So the default is now DEFERRED, not auto-launched. The pane, its chrome and its typing surface
  // all come up; the model SESSION is born on the operator's first message
  // (`handleOperatorText`), or when he presses the explicit "▶ live" control. Auto-launching at
  // startup spent a governed session on every app open, before anyone had asked for anything —
  // which is precisely what H-10 existed to stop, and LOCAL-01 D-4 measured H-10 as redundant
  // because the live gate already fails closed upstream. The deferred spawn is the protection that
  // replaces it, and it protects local attention as well as frontier quota: opening the shell no
  // longer loads a model into 8 GB of VRAM unasked.
  //
  // `SOW_CONDUCTOR_AUTOLAUNCH=1` is an explicit opt-in for anyone who wants the old behaviour; "0"
  // keeps its meaning (never launch), so the guard `sow.json` sets is unchanged and still honoured.
  if (!process.env.SHELL_SELFCHECK && process.env.SOW_CONDUCTOR_AUTOLAUNCH === "1") {
    try { await launchConductorSession({ reason: "conductor-first startup (SOW_CONDUCTOR_AUTOLAUNCH=1)" }); }
    catch (e) { log(`conductor: auto-launch failed (fail-closed, pane 1 un-launched): ${e && e.message}`); }
  } else if (!process.env.SHELL_SELFCHECK) {
    log("conductor: session deferred (option C) — nothing spawns until a model is selected and a "
      + "message is sent");
  }
  // In-Electron pane-I/O self-check (D-P16-0 binding): when SHELL_SELFCHECK is set, drive the REAL
  // renderer+PTY path inside this packaged runtime — spawn a supervised pane, assert its banner
  // renders into the xterm buffer, type a probe, assert the echo renders — and write a
  // machine-readable receipt. Then tear down (no orphan PTY/gateway, D-LOOP-1) and exit with the
  // pass/fail code. This is the guard the operator required: headless Node tests alone shipped a
  // runtime that failed at first launch; every 16A change is exercised in-runtime here.
  if (process.env.SHELL_SELFCHECK) {
    // Which in-Electron self-check to run (D-P16-0 is per-track): SHELL_SELFCHECK=picker → 16B picker;
    // =conductor → 16C conductor-selection badge; =conductor-spawn → 16C governed spawn of pane 1;
    // any other truthy value → 16A pane-I/O (back-compat).
    const kind = process.env.SHELL_SELFCHECK === "picker" ? "picker"
      : process.env.SHELL_SELFCHECK === "op12-picker" ? "op12-picker"
      : process.env.SHELL_SELFCHECK === "op12-acceptance" ? "op12-acceptance"
      : process.env.SHELL_SELFCHECK === "op12-live-acceptance" ? "op12-live-acceptance"
      : process.env.SHELL_SELFCHECK === "op18d-registration" ? "op18d-registration"
      : process.env.SHELL_SELFCHECK === "conductor" ? "conductor"
        : process.env.SHELL_SELFCHECK === "conductor-spawn" ? "conductor-spawn"
          : process.env.SHELL_SELFCHECK === "conductor-dispatch" ? "conductor-dispatch"
            : process.env.SHELL_SELFCHECK === "statusbar" ? "statusbar"
            : process.env.SHELL_SELFCHECK === "approvals" ? "approvals"
              : process.env.SHELL_SELFCHECK === "recovery" ? "recovery"
                : process.env.SHELL_SELFCHECK === "voice" ? "voice"
                : process.env.SHELL_SELFCHECK === "voice-probe" ? "voice-probe"
                : process.env.SHELL_SELFCHECK === "voice-mic" ? "voice-mic"
                : process.env.SHELL_SELFCHECK === "voice-conductor" ? "voice-conductor"
                  : process.env.SHELL_SELFCHECK === "assembled" ? "assembled"
                    : process.env.SHELL_SELFCHECK === "conductor-launch" ? "conductor-launch"
                      : process.env.SHELL_SELFCHECK === "conductor-pty" ? "conductor-pty"
                        : process.env.SHELL_SELFCHECK === "conductor-roundtrip" ? "conductor-roundtrip"
                          : process.env.SHELL_SELFCHECK === "worker-launch" ? "worker-launch"
                            : process.env.SHELL_SELFCHECK === "worker-spawn" ? "worker-spawn"
                            : process.env.SHELL_SELFCHECK === "pane-guards" ? "pane-guards"
                            : process.env.SHELL_SELFCHECK === "system-pane-write" ? "system-pane-write"
                            : process.env.SHELL_SELFCHECK === "readiness-window" ? "readiness-window"
                            : process.env.SHELL_SELFCHECK === "conductor-descriptor" ? "conductor-descriptor"
                            : process.env.SHELL_SELFCHECK === "runtime-honesty" ? "runtime-honesty"
                            : process.env.SHELL_SELFCHECK === "orchestration-collaboration"
                              ? "orchestration-collaboration"
                            : process.env.SHELL_SELFCHECK === "fully-live" ? "fully-live"
                              : "pane-io";
    let code = 1;
    try {
      await rendererReady;
      const ctx = {
        win,
        createPaneWithSession,
        isSupervised: () => Boolean(supervisor && supervisor.ready),
        conductorState,
        conductorFeed: () => conductorFeed,
        conductorSpawnFeed: () => conductorSpawn,
        conductorDispatchFeed: () => conductorDispatch,
        refreshApprovalModel,
        approvalModel: () => lastApprovalModel,
        // Phase 16D `.recovery` (U68) helpers: drive a simulated restart through the production path.
        loadLayoutSnapshot: () => recoveryStore.loadLayout(),
        reconstructLayout: () => reconstructConductorFirstLayout(),
        sendRecovery,
        // Phase 16E `.wire` (U67): the REAL production conductor-input delivery function, so the voice
        // self-check proves a routed CHAT transcript actually reaches an admitted pane's PTY (the live
        // interactive conductor session being operator-run/16F).
        deliverConductorChat,
        voiceAuthorityAudit: () => conductorVoiceAuthority.snapshot().audit,
        voiceAuthorityState: () => conductorVoiceAuthority.snapshot(),
        // Phase 17C `.close` (U164): the ephemeral loopback capability the supervised child is given,
        // so the receipt can dispatch a REAL hook event through the pinned command exactly as the
        // vendor would — instead of waiting for the live model to choose to call a tool.
        voiceAuthorityChildEnv: (base) => conductorVoiceAuthority.childEnv(base || {}),
        exerciseOperatorResumeGesture: () => {
          conductorVoiceAuthority.arm("operator recovery runtime check");
          let consumed = false;
          const handled = handleOperatorResumeInput(
            { preventDefault: () => { consumed = true; } },
            { type: "keyDown", key: "Escape", control: true, shift: true, isAutoRepeat: false },
          );
          const reset = conductorVoiceAuthority.snapshot().audit.findLast(
            (row) => row.event === "voice_turn_disarmed"
              && row.source === "electron_main_operator_chord");
          return { handled, consumed, reset: reset || null, turn: conductorVoiceAuthority.turnState() };
        },
        // Phase 17C `.disarm` (U166): the OTHER main-owned gesture — the operator simply TYPING. The
        // receipt drives the production `before-input-event` handler with an ordinary key, exactly as
        // an operator keystroke reaches it, and reads back what the supervisor decided.
        exerciseOperatorTypedKeyDisarm: () => {
          let consumed = false;
          const handled = handleOperatorResumeInput(
            { preventDefault: () => { consumed = true; } },
            { type: "keyDown", key: "a", control: false, shift: false, isAutoRepeat: false },
          );
          const disarmed = conductorVoiceAuthority.snapshot().audit.findLast(
            (row) => row.event === "voice_turn_disarmed"
              && row.source === "electron_main_before_input_event");
          return {
            handled,                       // false: an ordinary keystroke is NOT consumed by main…
            consumed,                      // …so it still reaches the pane the operator is typing into
            disarmed: disarmed || null,
            turn: conductorVoiceAuthority.turnState(),
          };
        },
        // Phase 17C `.disarm`: arm a supervisor-side turn with NO delivery, so the receipt can exercise
        // the OTHER release path (a turn still live when the supervised process dies). It writes
        // nothing to any session and spends no live exchange; the receipt discloses it.
        armVoiceTurnForExitCheck: () => conductorVoiceAuthority.arm(
          "supervisor-side turn armed by the in-Electron self-check to exercise the process-exit release"),
        // Phase 17C `.probe` (U74): the REAL production voice state + the shell's OWN probe instance,
        // so the receipt measures what the operator's chrome reads — not a test-only probe.
        voiceState: () => voiceState(),
        voiceProbe: () => ensureVoiceProbe(),
        // Phase 17A `.pty`: the REAL production launch path + its observable state, so the
        // in-Electron receipt exercises exactly what an operator launch does (no test-only spawn).
        launchConductorSession,
        conductorLaunchState,
        // Phase 17B `.spawn`: the REAL production picker→launch path (the exact function the
        // `pane:spawnFromSelection` IPC handler calls) + the observable per-pane launch record, so
        // the in-Electron receipt exercises what an operator's picker click does — no test-only spawn.
        spawnFromSelection,
        workerLaunchState,
        workerLauncher,
        // Phase 17B `.spawn-revalidate`: the pane CHROME as the shell actually holds it, so a receipt
        // leg can read what the operator's badge is drawn from AFTER a session ends — the ended-chrome
        // revision was a rule no test and no receipt leg could see (spec-audit MAJOR-2).
        paneChromeOf: (id) => paneChrome.get(id) || null,
        // …and the pinned pane-1 id, so the conductor-pane guard is exercised against the REAL
        // conductor pane rather than a hard-coded "pane-1" (validator MINOR-2).
        conductorPaneIdOf: () => conductorPaneId,
        paneModel: () => panes,
        // Phase 19 unit 19.3 (U328): the PRODUCTION system→pane write path and the refusal its
        // callers read, so the in-Electron receipt gates exactly what a peer message, a debate turn
        // or the conductor's readiness prompt goes through — not a re-creation of it.
        writePanePrompt,
        paneWriteRefusalFor,
        // Phase 19 unit 19.4 (U329): the PRODUCTION bounded window — the same instance readiness
        // classifies through — so the receipt measures this shell's real read of a real pane buffer
        // rather than a re-creation of it.
        readinessWindow,
        // Phase 19 unit 19.6 (U331/U333): the descriptor this shell ACTUALLY resolved — sourced
        // from the Python registry over the conductor feed, so the receipt admits the host's real
        // selection rather than one the check made up — and the PRODUCTION provider resolver the
        // write path uses, so a trait leg reads what a real pane's provider resolves to.
        conductorDescriptorOf: () => conductorDescriptor(),
        paneProviderFor,
        // …and the two remaining PRODUCTION bindings a readiness RUN needs, so the in-Electron
        // receipt can drive `createWorkerReadiness.run()` itself rather than only the window and the
        // ordering function (the checkpoint's owed leg). `setWorkerOperationalState` is the real
        // state writer — launch record, pane chrome, renderer push — so a leg that reaches READY or
        // STALLED moves what the operator's badge is drawn from. What the check supplies ITSELF is
        // eight bindings, not one: the MCP session state, the provider tool-call count (SIMULATED —
        // counted on prompt delivery, so the structured half of a promotion is the check's), the
        // last successful MCP operation, both deadlines, and now, sleep and log — plus a SEEDED
        // launch record per pane, because a self-check pane was never launched through the picker.
        // No live provider session exists in a check that spends no live exchange. The receipt
        // enumerates all of it (`check_owned_bindings`, `seeded_launch_record`), and this comment
        // counts what that list counts rather than saying "its own MCP session state" (U386(f)) —
        // and counts each binding once, which is what round 4 found it and the receipt both doing
        // wrong (U393 MINOR-4).
        setWorkerOperationalState,
        sessionManager: () => manager,
        // the REAL node-pty boundary: what the child was actually handed (env KEY NAMES only)
        ptySpawnObserved,
        killSession: (id) => { try { manager.kill(id); } catch { /* already terminal */ } },
        // Phase 17E: run the SAME governed dispatch the conductor chrome sources at launch, but ask
        // the emitter for a LIVE worker. It exists only here, inside the SHELL_SELFCHECK block, and
        // `apps/desktop/test/conductor-dispatch-live-workers.test.js` fails if it ever moves out or
        // if any launch-path call acquires the flag: a live dispatch at launch would spend one
        // governed exchange every time the operator opened the app, before anyone asked for anything.
        runGovernedDispatch: (opts) => sourceConductorDispatchFeed({
          cwd: REPO_ROOT,
          liveWorkers: (opts || {}).liveWorkers === true,
          timeoutMs: (opts || {}).timeoutMs,
        }),
        repoRoot: REPO_ROOT,
        // Phase 18C `.close`: the DURABLE sink this process's log really goes to, from the logger
        // that owns the path — so the §17 "no credential material in any log" scan reads the file
        // the shell wrote rather than one an env var happened to name (or, worse, treats an unset
        // env var as nothing to check).
        mainLogFile: mainProcessLogger.file,
        log,
      };
      const receipt = kind === "op12-live-acceptance"
        ? await runOp12LiveAcceptanceSelfCheck(ctx)
        : kind === "op18d-registration"
        ? await runOp18dRegistrationSelfCheck(ctx)
        : kind === "op12-acceptance"
        ? await runOp12AcceptanceSelfCheck(ctx)
        : kind === "op12-picker"
        ? await runOp12PickerSelfCheck(ctx)
        : kind === "picker"
        ? await runPickerSelfCheck(ctx)
        : kind === "conductor"
          ? await runConductorSelfCheck(ctx)
          : kind === "conductor-spawn"
            ? await runConductorSpawnSelfCheck(ctx)
            : kind === "conductor-dispatch"
              ? await runConductorDispatchSelfCheck(ctx)
              : kind === "statusbar"
                ? await runStatusBarSelfCheck(ctx)
                : kind === "approvals"
                  ? await runApprovalsSelfCheck(ctx)
                  : kind === "recovery"
                    ? await runRecoverySelfCheck(ctx)
                    : kind === "voice"
                      ? await runVoiceSelfCheck(ctx)
                      : kind === "voice-probe"
                        ? await runVoiceProbeSelfCheck(ctx)
                      : kind === "voice-mic"
                        ? await runVoiceMicSelfCheck(ctx)
                      : kind === "voice-conductor"
                        ? await runVoiceConductorSelfCheck(ctx)
                      : kind === "assembled"
                        ? await runAssembledSelfCheck(ctx)
                        : kind === "conductor-launch"
                          ? await runConductorLaunchSelfCheck(ctx)
                          : kind === "conductor-pty"
                            ? await runConductorPtySelfCheck(ctx)
                            : kind === "conductor-roundtrip"
                              ? await runConductorRoundTripSelfCheck(ctx)
                              : kind === "worker-launch"
                                ? await runWorkerLaunchSelfCheck(ctx)
                                : kind === "worker-spawn"
                                  ? await runWorkerSpawnSelfCheck(ctx)
                                  : kind === "pane-guards"
                                    ? await runPaneGuardsSelfCheck(ctx)
                                    : kind === "system-pane-write"
                                      ? await runSystemPaneWriteSelfCheck(ctx)
                                    : kind === "readiness-window"
                                      ? await runReadinessWindowSelfCheck(ctx)
                                    : kind === "conductor-descriptor"
                                      ? await runConductorDescriptorSelfCheck(ctx)
                                    : kind === "runtime-honesty"
                                      ? await runRuntimeHonestySelfCheck(ctx)
                                    : kind === "orchestration-collaboration"
                                      ? await runOrchestrationCollaborationSelfCheck(ctx)
                                    : kind === "fully-live"
                                      ? await runFullyLiveSelfCheck(ctx)
                                      : await runPaneIoSelfCheck(ctx);
      code = receipt && receipt.ok ? 0 : 1;
    } catch (e) {
      log(`[selfcheck] crashed: ${e.message}`);
    } finally {
      let cleanup = null;
      try {
        cleanup = await teardownSelfCheck();
      } catch (error) {
        code = 1;
        log(`[selfcheck] teardown failed: ${error && error.stack ? error.stack : error}`);
      }
      if (cleanup && !cleanup.complete) {
        code = 1;
        log(`[selfcheck] teardown incomplete: sessions=${JSON.stringify(cleanup.sessions.pending)}, `
          + `gatewayExited=${cleanup.gatewayExited}`);
      } else if (cleanup) {
        log("[selfcheck] teardown complete: zero managed terminal sessions; gateway exited");
      }
      // Drain pending writes and deliberately detach before the launcher closes the inherited pipe.
      // The durable file sink remains available throughout teardown.
      await mainProcessLogger.flushAndDetach();
      app.exit(code);      // pass/fail exit code for the node launcher
    }
  }
});
app.on("before-quit", (event) => {
  if (process.env.SHELL_SELFCHECK || normalQuitStarted) return;
  event.preventDefault();
  normalQuitStarted = true;
  completeNormalQuit().catch(async (error) => {
    log(`normal teardown failed: ${error && error.stack ? error.stack : error}`);
    try { await mainProcessLogger.flushAndDetach(); } catch { /* final exit must remain bounded */ }
    app.exit(1);
  });
});
// W-18a / R-12: there was NO handler for either process-level fault. Node >= 15 EXITS the process
// on an unhandled rejection, and teardown here is entirely cooperative through `before-quit` --
// which a fault exit does not run. So one missed `.catch()` orphaned every provider CLI, each
// holding a durable terminal whose `holder_pid` is THIS process: the ledger's dead-holder reaping
// cannot reclaim it, because the holder is the shell that just died skipping its own release.
//
// This is the SMALL half of R-12. OS-level containment -- a Job Object around the spawned tree, so
// a killed shell cannot leave a live provider process at all -- is W-18b. It crosses the
// Node/Python boundary and is deliberately NOT implemented here: it is held for an operator ruling.
let faultExitStarted = false;
function exitOnUnrecoverableFault(kind, err) {
  if (faultExitStarted || normalQuitStarted) return;
  faultExitStarted = true;
  normalQuitStarted = true;      // …so a before-quit racing this cannot start a second teardown
  try {
    log(`${kind}: ${err && err.stack ? err.stack : err} — releasing terminals before exit`);
  } catch { /* a logger fault must not mask the fault we are exiting on */ }
  completeNormalQuit(kind).catch(async (error) => {
    try {
      log(`teardown after ${kind} failed: ${error && error.stack ? error.stack : error}`);
    } catch { /* the final exit stays bounded */ }
    try { await mainProcessLogger.flushAndDetach(); } catch { /* bounded */ }
    app.exit(1);
  });
}
process.on("unhandledRejection", (reason) => exitOnUnrecoverableFault("unhandledRejection", reason));
process.on("uncaughtException", (error) => exitOnUnrecoverableFault("uncaughtException", error));
app.on("window-all-closed", () => app.quit());

module.exports = { resolveGateway, createPaneWithSession }; // for potential harnessing
