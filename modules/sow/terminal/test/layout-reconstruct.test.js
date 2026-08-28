"use strict";
/**
 * Conductor-first LAYOUT reconstruction (pure) — Phase 15E `.recovery`.
 *
 * After a full shell-process restart the workspace must come back with the pinned CONDUCTOR as
 * pane 1 (OP-7 §12.4, structural) and the worker panes reattaching to what existed — never as
 * naked live sessions (invariant 2, directive §9 track 14A). These headless tests prove the fold:
 * conductor-first is always present even with no snapshot; workers carry the session view's
 * dispositions; nothing is admitted during the recovery gap; the input is never mutated.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { PaneModel } = require("../compositor/pane-model");
const { SessionRegistry } = require("../session/session-registry");
const { reconstructSessions } = require("../recovery/reconstruct");
const {
  buildLayoutSnapshot,
  reconstructLayout,
  LAYOUT_FORMAT_VERSION,
} = require("../recovery/layout-reconstruct");

// -- buildLayoutSnapshot -------------------------------------------------------

test("buildLayoutSnapshot separates the conductor from workers and preserves order", () => {
  const panes = new PaneModel();
  panes.createPane({ id: "pane-1", sessionId: null, title: "CONDUCTOR" });
  panes.pin("pane-1");
  panes.createPane({ id: "pane-2", sessionId: "pane-2", title: "worker A" });
  panes.createPane({ id: "pane-3", sessionId: "pane-3", title: "worker B" });
  const meta = (id) => ({
    "pane-2": { role: "reasoning", mode: "autonomous", model: "opus-4.8", nodeId: "n2" },
    "pane-3": { role: "coding", mode: "attended", model: "gpt-5.5", nodeId: "n3" },
  }[id] || {});

  const snap = buildLayoutSnapshot({ panes, conductorPaneId: "pane-1", meta });
  assert.strictEqual(snap.version, LAYOUT_FORMAT_VERSION);
  assert.strictEqual(snap.conductor.paneId, "pane-1");
  assert.strictEqual(snap.conductor.pinned, true);
  assert.deepStrictEqual(snap.panes.map((p) => p.paneId), ["pane-2", "pane-3"]);
  assert.deepStrictEqual(snap.panes.map((p) => p.ordinal), [2, 3]);
  assert.strictEqual(snap.panes[0].role, "reasoning");
  assert.strictEqual(snap.panes[0].model, "opus-4.8");
  assert.strictEqual(snap.panes[1].mode, "attended", "attended chrome is captured");
});

test("buildLayoutSnapshot fail-closes an unknown worker mode to autonomous", () => {
  const panes = new PaneModel();
  panes.createPane({ id: "pane-2", sessionId: "pane-2", title: "w" });
  const snap = buildLayoutSnapshot({ panes, conductorPaneId: "pane-1", meta: () => ({ mode: "bogus" }) });
  assert.strictEqual(snap.panes[0].mode, "autonomous");
  assert.strictEqual(snap.conductor, null, "no conductor pane present ⇒ null in the snapshot");
});

// -- reconstructLayout: conductor-first is structural --------------------------

test("reconstructLayout ALWAYS yields a pinned pane-1 CONDUCTOR, even with no snapshot", () => {
  const layout = reconstructLayout({ snapshot: null, sessions: [], admissionOpen: true, selection: { model: "fable-5" } });
  assert.strictEqual(layout.conductor.ordinal, 1);
  assert.strictEqual(layout.conductor.role, "conductor");
  assert.strictEqual(layout.conductor.label, "CONDUCTOR");
  assert.strictEqual(layout.conductor.pinned, true);
  assert.strictEqual(layout.conductor.model, "fable-5");
  assert.strictEqual(layout.conductor.nodeState, "awaiting_live_conductor");
  assert.strictEqual(layout.conductor.reattach, false, "the conductor is re-established via the governed live launch, never auto-attached");
  // admission is OPEN here ⇒ the conductor MAY be (re)launched by the operator — but reattach stays
  // false + nodeState awaiting_live_conductor keep it non-live; `admitted` only reflects the channel.
  assert.strictEqual(layout.conductor.admitted, true, "channel verified ⇒ operator may launch; still not auto-attached");
  assert.deepStrictEqual(layout.panes, []);
});

test("reconstructLayout shows the SELECTION label, never a fabricated checkpoint (invariant 3)", () => {
  const layout = reconstructLayout({ snapshot: null, sessions: [], admissionOpen: true, selection: null });
  assert.strictEqual(layout.conductor.model, "(unknown selection)");
  assert.strictEqual(layout.conductor.verified, false);
});

// -- reconstructLayout: no naked re-spawn (invariant 2) ------------------------

test("a worker whose session was still alive at the cut needs supervised relaunch, never auto-attached", () => {
  const reg = new SessionRegistry();
  let t = 0; const ts = () => `t${t++}`;
  reg.register("pane-2", { nodeId: "n2", pid: 200 }, ts());
  reg.transition("pane-2", "RUNNING", ts(), {});
  // no terminal event: the PTY died with the shell
  const sessions = reconstructSessions(reg.eventLog());

  const snapshot = {
    version: 1,
    conductor: { paneId: "pane-1", pinned: true, model: "fable-5", sessionId: null },
    panes: [{ paneId: "pane-2", ordinal: 2, role: "coding", mode: "autonomous", model: "gpt-5.5", pinned: false, sessionId: "pane-2" }],
  };
  const layout = reconstructLayout({ snapshot, sessions, admissionOpen: true, selection: { model: "fable-5" } });
  const w = layout.panes[0];
  assert.strictEqual(w.paneId, "pane-2");
  assert.strictEqual(w.disposition, "interrupted");
  assert.strictEqual(w.needsRelaunch, true);
  assert.strictEqual(w.reattach, false, "no naked re-spawn (invariant 2)");
  assert.strictEqual(w.admitted, false, "re-admitted only through supervised relaunch");
  assert.strictEqual(w.paneState, "awaiting_supervision");
  assert.deepStrictEqual(layout.interrupted, ["pane-2"]);
});

test("a cleanly EXITED worker reconstructs as ended history, not needing relaunch", () => {
  const reg = new SessionRegistry();
  let t = 0; const ts = () => `t${t++}`;
  reg.register("pane-2", { nodeId: "n2", pid: 200 }, ts());
  reg.transition("pane-2", "RUNNING", ts(), {});
  reg.transition("pane-2", "EXITED", ts(), { exitCode: 0 });
  const sessions = reconstructSessions(reg.eventLog());
  const snapshot = { version: 1, conductor: null, panes: [{ paneId: "pane-2", ordinal: 2, sessionId: "pane-2" }] };

  const layout = reconstructLayout({ snapshot, sessions, admissionOpen: true });
  const w = layout.panes[0];
  assert.strictEqual(w.disposition, "exited");
  assert.strictEqual(w.needsRelaunch, false);
  assert.strictEqual(w.paneState, "ended");
  assert.deepStrictEqual(layout.interrupted, []);
});

test("a pane whose session has NO lifecycle record has an unknown fate ⇒ fail-closed to relaunch", () => {
  const snapshot = { version: 1, conductor: null, panes: [{ paneId: "pane-2", ordinal: 2, sessionId: "ghost-session" }] };
  const layout = reconstructLayout({ snapshot, sessions: [], admissionOpen: true });
  const w = layout.panes[0];
  assert.strictEqual(w.disposition, "absent");
  assert.strictEqual(w.needsRelaunch, true, "never assume a clean exit for a session we cannot see");
  assert.strictEqual(w.reattach, false);
});

test("a placeholder pane with no session needs no relaunch", () => {
  const snapshot = { version: 1, conductor: null, panes: [{ paneId: "pane-2", ordinal: 2, sessionId: null }] };
  const layout = reconstructLayout({ snapshot, sessions: [], admissionOpen: true });
  assert.strictEqual(layout.panes[0].disposition, "none");
  assert.strictEqual(layout.panes[0].needsRelaunch, false);
  assert.strictEqual(layout.panes[0].paneState, "empty");
});

// -- reconstructLayout: no admission during the gap (fail-closed) --------------

test("while the channel is NOT re-verified, NOTHING is admitted — no naked session during the gap", () => {
  const snapshot = {
    version: 1,
    conductor: { paneId: "pane-1", pinned: true, sessionId: null },
    panes: [{ paneId: "pane-2", ordinal: 2, sessionId: "pane-2" }],
  };
  const layout = reconstructLayout({ snapshot, sessions: [], admissionOpen: false, selection: { model: "fable-5" } });
  assert.strictEqual(layout.admissionOpen, false);
  assert.strictEqual(layout.conductor.admitted, false, "the conductor is not admitted until the channel re-verifies");
  assert.strictEqual(layout.panes[0].admitted, false);
  assert.strictEqual(layout.summary.admissionOpen, false);
});

// -- round-trip + determinism --------------------------------------------------

test("a full round-trip proves conductor-first layout recovery across a restart", () => {
  // shell #1: a conductor pane + two workers; one worker exits cleanly, one stays alive
  const panes = new PaneModel();
  panes.createPane({ id: "pane-1", sessionId: null, title: "CONDUCTOR" });
  panes.pin("pane-1");
  panes.createPane({ id: "pane-2", sessionId: "pane-2", title: "worker A" });
  panes.createPane({ id: "pane-3", sessionId: "pane-3", title: "worker B" });
  const meta = (id) => ({ "pane-2": { role: "reasoning", model: "opus-4.8" }, "pane-3": { role: "coding", model: "gpt-5.5" } }[id] || {});
  const snapshot = buildLayoutSnapshot({ panes, conductorPaneId: "pane-1", meta });

  const reg = new SessionRegistry();
  let t = 0; const ts = () => `t${t++}`;
  reg.register("pane-2", { nodeId: "n2", pid: 200 }, ts());
  reg.transition("pane-2", "RUNNING", ts(), {});
  reg.transition("pane-2", "EXITED", ts(), { exitCode: 0 });
  reg.register("pane-3", { nodeId: "n3", pid: 300 }, ts());
  reg.transition("pane-3", "RUNNING", ts(), {}); // still alive at the cut
  const sessions = reconstructSessions(reg.eventLog());

  // shell #2 boots: serialize both through JSON (what the disk round-trip does) and fold
  const layout = reconstructLayout({
    snapshot: JSON.parse(JSON.stringify(snapshot)),
    sessions: JSON.parse(JSON.stringify(sessions)),
    admissionOpen: true,
    selection: { model: "fable-5" },
  });

  assert.strictEqual(layout.conductor.paneId, "pane-1");
  assert.strictEqual(layout.conductor.pinned, true);
  assert.deepStrictEqual(layout.panes.map((p) => p.paneId), ["pane-2", "pane-3"]);
  assert.strictEqual(layout.panes[0].needsRelaunch, false, "the cleanly-exited worker is history");
  assert.strictEqual(layout.panes[1].needsRelaunch, true, "the still-alive worker needs supervised relaunch");
  assert.deepStrictEqual(layout.interrupted, ["pane-3"]);
  assert.strictEqual(layout.summary.total, 3);
  assert.strictEqual(layout.summary.workers, 2);
  assert.strictEqual(layout.summary.interrupted, 1);
});

// -- Phase 16D `.recovery` (U68): worker-pane CHROME survives the round-trip --------

test("buildLayoutSnapshot captures the governed worker chrome (badge) from meta().chrome (U68)", () => {
  const panes = new PaneModel();
  panes.createPane({ id: "pane-2", sessionId: "pane-2", title: "w" });
  const meta = () => ({
    role: "reasoning", mode: "autonomous", model: "opus-4.8",
    chrome: {
      provider: "claude_code", adapter: "claude_code_cli", locality: "frontier",
      model_label: "opus-4.8", model_slug: "claude-opus-4-8", model_verified: false,
      role: "reasoning", mode: "autonomous", node_state: "selected_awaiting_governed_spawn",
      governed: false, subscription: { allowance: 2, in_use: null }, residency: null,
      // a stray field the caller might carry — must NOT survive (deterministic whitelist)
      secret: "leak",
    },
  });
  const snap = buildLayoutSnapshot({ panes, conductorPaneId: "pane-1", meta });
  const c = snap.panes[0].chrome;
  assert.strictEqual(c.model_label, "opus-4.8");
  assert.strictEqual(c.model_slug, "claude-opus-4-8");
  assert.strictEqual(c.locality, "frontier");
  assert.strictEqual(c.node_state, "selected_awaiting_governed_spawn");
  assert.strictEqual(c.governed, false, "the recorded selection never claims a live governed node");
  assert.deepStrictEqual(c.subscription, { allowance: 2, in_use: null });
  assert.strictEqual(c.secret, undefined, "only whitelisted chrome fields survive (no blind copy)");
});

test("a worker with no recorded selection snapshots chrome:null (honest, never a fabricated model)", () => {
  const panes = new PaneModel();
  panes.createPane({ id: "pane-2", sessionId: "pane-2", title: "w" });
  const snap = buildLayoutSnapshot({ panes, conductorPaneId: "pane-1", meta: () => ({}) });
  assert.strictEqual(snap.panes[0].chrome, null);
  assert.strictEqual(snap.panes[0].model, null);
});

test("reconstructLayout carries the worker chrome across the restart fold, re-sanitized (U68)", () => {
  const snapshot = {
    version: 1,
    conductor: null,
    panes: [{
      paneId: "pane-2", ordinal: 2, sessionId: null,
      chrome: {
        provider: "codex", locality: "frontier", model_label: "gpt-5.5", model_slug: "gpt-5.5",
        model_verified: true, role: "coding", mode: "attended",
        node_state: "selected_awaiting_governed_spawn", governed: false,
        subscription: { allowance: 2, in_use: 1 }, residency: null,
      },
    }],
  };
  const layout = reconstructLayout({ snapshot, sessions: [], admissionOpen: false, selection: { model: "fable-5" } });
  const w = layout.panes[0];
  assert.strictEqual(w.chrome.model_label, "gpt-5.5");
  assert.strictEqual(w.chrome.model_verified, true);
  assert.strictEqual(w.chrome.node_state, "selected_awaiting_governed_spawn");
  assert.deepStrictEqual(w.chrome.subscription, { allowance: 2, in_use: 1 });
  // U68 chrome does NOT weaken the invariant-2 guards: still not reattached / not admitted on boot.
  assert.strictEqual(w.reattach, false, "carrying chrome never auto-attaches a live session (invariant 2)");
  assert.strictEqual(w.admitted, false);
});

// ---- a restored chrome may never claim a LIVE node (17B `.spawn-revalidate`) -------------------
// The shell that wrote the snapshot was KILLED — no exit event fired, so `markWorkerPaneChromeEnded`
// never ran and `{node_state:"running", governed:true}` reached disk. The renderer draws
// node_state==="running" as the badge text `live`, and on the next boot paneSeq restarts at 0, so
// the operator's first new worker pane takes the same id the stale entry holds: a brand-new empty
// pane came up badged `live` for a process that died with the last shell (gate-validator MAJOR-1 /
// spec-audit MAJOR-1, 2026-07-26). Reconstruction knows better than the snapshot here — it admits
// nothing and reattaches nothing — so it rewrites the claim rather than carrying it.
const KILLED_SNAPSHOT = (over = {}) => ({
  version: 1,
  conductor: null,
  panes: [{
    paneId: "pane-2", ordinal: 2, sessionId: null,
    chrome: {
      provider: "anthropic", adapter: "claude_code", locality: "frontier",
      model_label: "Fable 5", model_slug: "fable-5", model_verified: true,
      role: "reasoning", mode: "autonomous",
      node_state: "running", governed: true,
      subscription: { allowance: 2, in_use: 1 }, residency: null, ...over,
    },
  }],
});

test("a snapshot written by a KILLED shell comes back INTERRUPTED, never `running` (invariant 3)", () => {
  const layout = reconstructLayout({ snapshot: KILLED_SNAPSHOT(), sessions: [], admissionOpen: true });
  const c = layout.panes[0].chrome;
  assert.strictEqual(c.node_state, "session_interrupted", "a restored pane may not claim a live node");
  assert.strictEqual(c.governed, false, "there is no governed node in this pane after a restart");
  // the FACT is kept, not erased: the pane WAS running, which is the true statement the snapshot
  // supports — in place of the false one ("is running") it used to make.
  assert.strictEqual(c.interrupted_from, "running");
  // …and the model badge is untouched: the operator picked it and it is what the pane last ran.
  assert.strictEqual(c.model_label, "Fable 5");
  assert.strictEqual(c.model_verified, true);
});

test("every LIVE node_state is rewritten, not just `running` (the badge maps more than one)", () => {
  for (const live of ["running", "launching", "session_terminating", "ready", "live", "RUNNING"]) {
    const layout = reconstructLayout({ snapshot: KILLED_SNAPSHOT({ node_state: live }), sessions: [] });
    assert.strictEqual(layout.panes[0].chrome.node_state, "session_interrupted", `${live} survived the fold`);
    assert.strictEqual(layout.panes[0].chrome.interrupted_from, live);
  }
});

test("a chrome that says governed:true with a dead state still comes back UNGOVERNED", () => {
  const layout = reconstructLayout({
    snapshot: KILLED_SNAPSHOT({ node_state: "session_exited", governed: true }), sessions: [],
  });
  const c = layout.panes[0].chrome;
  assert.strictEqual(c.governed, false);
  assert.strictEqual(c.node_state, "session_exited", "an already-honest state is not rewritten");
  assert.strictEqual(c.interrupted_from, null);
});

test("a forged `interrupted_from` in the snapshot is DERIVED, never carried through the fold", () => {
  const snap = KILLED_SNAPSHOT({ node_state: "session_killed", governed: false });
  snap.panes[0].chrome.interrupted_from = "running";  // a corrupt/forged snapshot claiming a run
  const layout = reconstructLayout({ snapshot: snap, sessions: [] });
  assert.strictEqual(layout.panes[0].chrome.interrupted_from, null,
    "interrupted_from is derived at the fold; the whitelist drops whatever disk supplied");
});

test("reconstructLayout fail-closes a corrupt worker chrome to null (never propagates garbage)", () => {
  const snapshot = { version: 1, conductor: null, panes: [{ paneId: "pane-2", ordinal: 2, sessionId: null, chrome: "not-an-object" }] };
  const layout = reconstructLayout({ snapshot, sessions: [], admissionOpen: true });
  assert.strictEqual(layout.panes[0].chrome, null);
});

test("reconstructLayout is deterministic and does not mutate its inputs", () => {
  const snapshot = { version: 1, conductor: { paneId: "pane-1" }, panes: [{ paneId: "pane-2", sessionId: "pane-2" }] };
  const sessions = [{ id: "pane-2", disposition: "interrupted", needsRelaunch: true, lastState: "RUNNING" }];
  const snapBefore = JSON.stringify(snapshot);
  const sessBefore = JSON.stringify(sessions);
  const a = reconstructLayout({ snapshot, sessions, admissionOpen: true });
  const b = reconstructLayout({ snapshot, sessions, admissionOpen: true });
  assert.deepStrictEqual(a, b);
  assert.strictEqual(JSON.stringify(snapshot), snapBefore, "snapshot is read, never written");
  assert.strictEqual(JSON.stringify(sessions), sessBefore, "session view is read, never written");
});

// ---- W-64: pane id collision across restart ---------------------------------
// The recovery snapshot reuses the `pane-N` namespace while the shell's mint
// counter restarted at 0 on every boot, so a fresh bare shell could take over an
// id a dead governed pane still holds in the persisted layout - and inherit that
// pane's model badge. resumePaneSeq is the seeding contract: new mints start
// ABOVE every id the snapshot holds; existing snapshots rehydrate untouched.

const fs = require("node:fs");
const path = require("node:path");
const {
  buildLayoutSnapshot: _bls,
  reconstructLayout: _rl,
  resumePaneSeq,
} = require("../recovery/layout-reconstruct");

function w64SnapshotWithGovernedWorkerAtPane2() {
  const panes = new PaneModel();
  panes.createPane({ id: "pane-1", sessionId: null, title: "CONDUCTOR" });
  panes.pin("pane-1");
  panes.createPane({ id: "pane-2", sessionId: "pane-2", title: "worker" });
  const meta = (id) => (id === "pane-1"
    ? { role: "conductor", mode: "attended", model: "codex-gpt-5.6-sol" }
    : { role: "worker", mode: "autonomous", model: "grok-4.5",
        chrome: { provider: "x.ai", adapter: "grok_build", locality: "remote",
          model_label: "grok-4.5", model_slug: "grok-4.5", model_verified: true,
          role: "worker", mode: "autonomous", node_state: "session_exited",
          governed: true } });
  return buildLayoutSnapshot({ panes, conductorPaneId: "pane-1", meta });
}

test("W-64 defect arithmetic: re-minting from zero takes an id the snapshot holds", () => {
  const snapshot = w64SnapshotWithGovernedWorkerAtPane2();
  const held = new Set([snapshot.conductor.paneId, ...snapshot.panes.map((w) => w.paneId)]);
  // the pre-repair mint sequence on a restarted shell: conductor first, then a bare shell
  let seq = 0;
  const minted = [`pane-${++seq}`, `pane-${++seq}`];
  const collided = minted.filter((id) => held.has(id));
  assert.ok(collided.length > 0,
    "the hazard this card closes: an unseeded restart re-mints a persisted governed pane id");
});

test("resumePaneSeq seeds above every id the snapshot holds so no mint ever collides", () => {
  const snapshot = w64SnapshotWithGovernedWorkerAtPane2();
  const held = new Set([snapshot.conductor.paneId, ...snapshot.panes.map((w) => w.paneId)]);
  const seeded = resumePaneSeq({ snapshot, paneSeq: 0 });
  assert.strictEqual(seeded, 2, "floor is the highest held ordinal (conductor pane-1, worker pane-2)");
  for (let i = 1; i <= 5; i++) {
    assert.strictEqual(held.has(`pane-${seeded + i}`), false,
      `mint pane-${seeded + i} must be outside the persisted namespace`);
  }
});

test("resumePaneSeq never lowers a live counter and ignores corrupt snapshots", () => {
  assert.strictEqual(resumePaneSeq({ snapshot: null, paneSeq: 4 }), 4);
  assert.strictEqual(resumePaneSeq({ snapshot: undefined, paneSeq: 0 }), 0);
  assert.strictEqual(resumePaneSeq({ snapshot: { version: 1 }, paneSeq: 3 }), 3);
  assert.strictEqual(
    resumePaneSeq({ snapshot: { conductor: { paneId: "not-a-pane-id" }, panes: [{ paneId: "../forged" }] }, paneSeq: 1 }),
    1, "non pane-N ids contribute nothing");
  assert.strictEqual(resumePaneSeq({ snapshot: w64SnapshotWithGovernedWorkerAtPane2(), paneSeq: 9 }), 9,
    "a live counter already ahead of the snapshot is never rewound");
});

test("main.js seeds the mint counter at did-finish-load AFTER the structural conductor mint", () => {
  const src = fs.readFileSync(path.join(__dirname, "..", "..", "apps", "desktop", "main.js"), "utf8");
  const importLine = src.indexOf("resumePaneSeq");
  assert.notStrictEqual(importLine, -1, "main.js imports resumePaneSeq");
  const requireBlock = src.slice(0, src.indexOf("let paneSeq"));
  assert.ok(requireBlock.includes("resumePaneSeq"), "imported from terminal/recovery/layout-reconstruct beside the fold");
  const bootAnchor = src.indexOf("createConductorPane(); // conductor-first");
  assert.notStrictEqual(bootAnchor, -1);
  const window = src.slice(bootAnchor, bootAnchor + 800);
  const seedCall = window.search(/paneSeq\s*=\s*Math\.max\(\s*paneSeq\s*,\s*resumePaneSeq\(/);
  assert.notStrictEqual(seedCall, -1,
    "the seed sits inside did-finish-load immediately after the conductor mint, before any worker mint");
});