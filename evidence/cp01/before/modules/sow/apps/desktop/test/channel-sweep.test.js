"use strict";
/**
 * Phase 17C `.receipt` — U177, the half of the disarm property that **no source reading can see**.
 *
 * `voice-disarm-wiring.test.js` closed every STATIC form: no `ipcMain.handle` body, and nothing
 * reachable by name from one, calls a release or so much as names the authority service. Its own
 * header says what that leaves open, and the register carries it as U177:
 *
 *   > a callee reached through a getter or a Proxy trap, or a reference stored on one channel and
 *   > invoked from another … The wider property — **no renderer IPC channel may release an ADMITTED
 *   > turn** — is therefore a RUNTIME assertion and is owed as one: arm a turn in the packaged check,
 *   > drive every renderer channel, assert the turn is still admitted.
 *
 * This file is the headless half of that: the sweep DRIVER and the survival VERDICT, both pure, both
 * falsifiable without Electron. The in-Electron half — the actual drive against the real preload
 * surface while a real live voice turn is admitted — is a leg of `voice-conductor-selfcheck.js`,
 * because that is the only place an admitted turn exists.
 *
 * The load-bearing property here is COVERAGE, and it is fail-closed in both directions: a channel
 * `main.js` registers but the sweep does not drive, or a method `preload.js` exposes that the sweep
 * does not name, makes the sweep report `ok:false` — a runtime assertion that silently skipped the
 * one new channel would be worse than no assertion at all, because the receipt would still be green.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const {
  SWEEP, runChannelSweep, registeredIpcChannels, ipcRegistrationCounts, exposedInvokeChannels,
  exposedStreamMethods, preloadCounts, CONDUCTOR_SAFE_METHODS, CONDUCTOR_INPUT_BYTES,
} = require("../renderer/channel-sweep");
const { turnSurvivedChannelSweep } = require("../voice/turn-survival");

const DESKTOP = path.resolve(__dirname, "..");
const MAIN_SRC = fs.readFileSync(path.join(DESKTOP, "main.js"), "utf8");
const PRELOAD_SRC = fs.readFileSync(path.join(DESKTOP, "preload.js"), "utf8");

/** A surface that answers every sweep method, recording the order and arguments it was called with. */
function fakeSurface({ omit = [], throws = [] } = {}) {
  const calls = [];
  const surface = {
    // main → renderer streams: not invocations, and the sweep must not try to "drive" them
    onData() {}, onState() {}, onLayout() {}, onLog() {}, onRecovery() {},
    onConductor() {}, onPaneChrome() {}, onApprovals() {}, onVoice() {},
  };
  for (const entry of SWEEP) {
    if (omit.includes(entry.method)) continue;
    surface[entry.method] = async (...args) => {
      calls.push({ method: entry.method, args });
      if (throws.includes(entry.method)) throw new Error(`${entry.method} refused`);
      return entry.method === "newPane" ? "pane-scratch-7" : { ok: true };
    };
  }
  return { surface, calls };
}

const CTX = { conductorPaneId: "pane-1", cols: 120, rows: 40 };

// ---- coverage: the sweep is closed against BOTH sides of the bridge -------------------------

test("every IPC channel main.js registers is driven by the sweep (U177)", () => {
  const registered = registeredIpcChannels(MAIN_SRC);
  assert.ok(registered.length > 15, `expected main's IPC channels, parsed ${registered.length}`);
  const driven = new Set(SWEEP.map((e) => e.channel));
  for (const channel of registered) {
    assert.ok(driven.has(channel),
      `main.js registers ${channel} and the U177 runtime sweep does not drive it. A renderer channel `
      + "nobody drives is exactly where a dynamic release would sit — add it to SWEEP with safe "
      + "arguments, do not narrow the claim.");
  }
});

test("every invoke method preload.js exposes is named by the sweep (U177)", () => {
  const exposed = exposedInvokeChannels(PRELOAD_SRC);
  assert.ok(exposed.length > 15, `expected the preload bridge's methods, parsed ${exposed.length}`);
  const byMethod = new Map(SWEEP.map((e) => [e.method, e.channel]));
  for (const { method, channel } of exposed) {
    assert.ok(byMethod.has(method), `preload exposes ${method}() and the sweep does not drive it`);
    assert.equal(byMethod.get(method), channel,
      `the sweep maps ${method}() to ${byMethod.get(method)}, but preload sends it to ${channel}`);
  }
  // …and closed downward: an entry for a method the bridge no longer exposes is a sweep that reports
  // coverage it does not have.
  const exposedMethods = new Set(exposed.map((e) => e.method));
  for (const entry of SWEEP) {
    assert.ok(exposedMethods.has(entry.method),
      `SWEEP drives ${entry.method}(), which preload.js no longer exposes — remove the stale entry`);
  }
});

test("the parsers refuse rather than under-report: every registration is one they can name", () => {
  // `registeredIpcChannels` reads ONE shape (a double-quoted literal). A registration in any other
  // shape — a channel name in a constant, a one-way `ipcMain.on` — would be invisible to it, and an
  // invisible channel is an undriven one the sweep would still call complete (validator R-4).
  const counts = ipcRegistrationCounts(MAIN_SRC);
  assert.equal(counts.parsed, counts.handle_total,
    "main.js registers an IPC channel in a shape the coverage parser cannot name. Either write it as "
    + 'ipcMain.handle("<literal>", …) or teach the parser — do not leave a channel outside the sweep.');
  assert.equal(counts.one_way_total, 0,
    "main.js registers a one-way ipcMain.on channel. The sweep drives invoke channels; a one-way "
    + "channel is renderer bytes too, and nothing here would drive it.");
  const pre = preloadCounts(PRELOAD_SRC);
  assert.equal(exposedInvokeChannels(PRELOAD_SRC).length, pre.invoke_total,
    "an ipcRenderer.invoke in preload.js was not attributed to a method name by the parser");
  assert.equal(exposedStreamMethods(PRELOAD_SRC).length, pre.on_total,
    "an ipcRenderer.on in preload.js was not attributed to a method name by the parser");
  for (const entry of [...exposedInvokeChannels(PRELOAD_SRC), ...exposedStreamMethods(PRELOAD_SRC)]) {
    assert.ok(entry.method, `a bridge entry for ${entry.channel} has no readable method name`);
  }
});

test("the keys the sweep skips at runtime are exactly the bridge's stream subscribers", () => {
  // `runChannelSweep` skips `/^on[A-Z]/` keys as main→renderer streams. That is a hole unless those
  // keys really are subscribers — a future `onDemandSpawn()` intent would be skipped in silence
  // (spec-audit F8). Asserted here, against the real bridge.
  const streams = new Set(exposedStreamMethods(PRELOAD_SRC).map((e) => e.method));
  const invokes = new Set(exposedInvokeChannels(PRELOAD_SRC).map((e) => e.method));
  for (const method of streams) {
    assert.match(method, /^on[A-Z]/, `${method}() subscribes to a stream but the sweep would try to drive it`);
  }
  for (const method of invokes) {
    assert.doesNotMatch(method, /^on[A-Z]/,
      `${method}() is an INVOKE the runtime sweep would skip as a stream subscriber`);
  }
});

test("what the sweep writes into the LIVE conductor cannot become a prompt", () => {
  // The first version typed its probe STRING into pane 1 with a trailing ETX and claimed that cleared
  // the line. It did not: the live CLI took the ETX as an interrupt, kept the text, and the operator's
  // next typed prompt was submitted with it attached (validator RESERVATION-3 / spec-audit F1).
  const entry = SWEEP.find((e) => e.method === "input");
  const [, payload] = entry.args({ conductorPaneId: "pane-1" });
  assert.equal(payload, CONDUCTOR_INPUT_BYTES);
  assert.match(payload, /^[\x00-\x1f]+$/,
    "the conductor-pane write must be control bytes only — printable text survives in the CLI's input "
    + "box and becomes part of whatever the operator sends next");
  assert.ok(!payload.includes("\r") && !payload.includes("\n"),
    "…and must not submit anything: a bare CR answers whatever prompt the pane happens to be showing");
  assert.ok(!payload.includes("\x03"),
    "…and must not be ETX: the live CLI answers it with 'press Ctrl-C again to exit', which is an "
    + "interrupt rather than a clear, and a second one ends the operator's session");
  for (const other of SWEEP) {
    if (other.pane !== "conductor" || other.method === "input") continue;
    const args = other.args({ conductorPaneId: "pane-1", cols: 80, rows: 24 });
    assert.ok(!args.some((a) => typeof a === "string" && a.includes("sovereign-channel-sweep")),
      `${other.method}() carries sweep text to the live conductor pane`);
  }
});

test("the destructive pane intents never target the conductor pane", () => {
  for (const entry of SWEEP) {
    if (entry.pane !== "conductor") continue;
    assert.ok(CONDUCTOR_SAFE_METHODS.has(entry.method),
      `${entry.method}() is driven against the LIVE conductor pane. Only the non-destructive intents `
      + "may be: killing, hiding or re-tiling pane 1 mid-run would destroy the live session this "
      + "receipt is measuring. Point it at the scratch pane instead.");
  }
  // …and the ones that CAN destroy a pane must be exercised somewhere, or the sweep is not driving
  // the channels it claims to.
  for (const method of ["close", "maximize", "minimize", "restore", "pin"]) {
    const entry = SWEEP.find((e) => e.method === method);
    assert.ok(entry && entry.pane === "scratch", `${method}() must be driven against the scratch pane`);
  }
});

// ---- the driver ------------------------------------------------------------------------------

test("the sweep drives every channel once, scratch pane created first and closed after", async () => {
  const { surface, calls } = fakeSurface();
  const res = await runChannelSweep(surface, CTX);
  assert.equal(res.ok, true, `sweep not ok: ${JSON.stringify(res.uncovered)} ${JSON.stringify(res.missing)}`);
  assert.equal(res.channels.length, SWEEP.length);
  assert.ok(res.channels.every((c) => c.invoked === true), "every channel must be invoked");
  assert.deepEqual(calls.map((c) => c.method).sort(), SWEEP.map((e) => e.method).sort());
  const order = calls.map((c) => c.method);
  assert.equal(order[0], "newPane", "the scratch pane must exist before anything targets it");
  for (const scratch of SWEEP.filter((e) => e.pane === "scratch")) {
    assert.ok(order.indexOf(scratch.method) > order.indexOf("newPane"),
      `${scratch.method}() ran before the scratch pane existed`);
  }
  assert.equal(order[order.length - 1], "close", "the scratch pane must be closed last");
  // the scratch-targeted calls carry the id the create returned, never the conductor's
  for (const call of calls) {
    const entry = SWEEP.find((e) => e.method === call.method);
    if (entry.pane === "scratch") assert.equal(call.args[0], "pane-scratch-7", `${call.method} targeted the wrong pane`);
    if (entry.pane === "conductor") assert.equal(call.args[0], "pane-1", `${call.method} targeted the wrong pane`);
  }
  assert.equal(res.scratch_pane_id, "pane-scratch-7");
});

test("a channel the bridge exposes and the sweep does not know is a FAILED sweep", async () => {
  const { surface } = fakeSurface();
  surface.someNewIntent = async () => ({ ok: true });
  const res = await runChannelSweep(surface, CTX);
  assert.equal(res.ok, false);
  assert.deepEqual(res.uncovered, ["someNewIntent"]);
});

test("a sweep method the bridge does not answer is a FAILED sweep, not a skipped one", async () => {
  const { surface } = fakeSurface({ omit: ["voiceState"] });
  const res = await runChannelSweep(surface, CTX);
  assert.equal(res.ok, false);
  assert.deepEqual(res.missing, ["voiceState"]);
  const row = res.channels.find((c) => c.method === "voiceState");
  assert.equal(row.invoked, false);
});

test("a handler that throws was still DRIVEN — the property is about the turn, not the reply", async () => {
  const { surface } = fakeSurface({ throws: ["launchConductor", "spawnFromSelection"] });
  const res = await runChannelSweep(surface, CTX);
  assert.equal(res.ok, true);
  const row = res.channels.find((c) => c.method === "launchConductor");
  assert.equal(row.invoked, true);
  assert.match(row.error, /launchConductor refused/);
});

test("with no conductor pane the sweep refuses rather than driving a wrong pane", async () => {
  const { surface, calls } = fakeSurface();
  const res = await runChannelSweep(surface, { cols: 80, rows: 24 });
  assert.equal(res.ok, false);
  assert.ok(res.channels.some((c) => c.pane === "conductor" && c.invoked === false));
  assert.ok(!calls.some((c) => SWEEP.find((e) => e.method === c.method).pane === "conductor"));
});

test("if the scratch pane cannot be created, its intents are refused, not aimed elsewhere", async () => {
  const surface = fakeSurface().surface;
  surface.newPane = async () => null;                       // supervision denied, say
  const res = await runChannelSweep(surface, CTX);
  assert.equal(res.ok, false);
  for (const row of res.channels.filter((c) => c.pane === "scratch")) {
    assert.equal(row.invoked, false, `${row.method} was invoked with no scratch pane to target`);
  }
});

// ---- the verdict -----------------------------------------------------------------------------

const TURN = "turn-abc";
const ARMED_ROW = { event: "voice_turn_armed", turn_id: TURN };
const OK_STATE = {
  active: { turn_id: TURN, session_id: "s1" },
  turn: { restricted: true, phase: "active", turn_id: TURN, tools_denied: true },
};
const OK_SWEEP = { ok: true, channels: [{ method: "input", invoked: true }] };
const survival = (over) => turnSurvivedChannelSweep({
  turnId: TURN, before: [ARMED_ROW], after: [ARMED_ROW], stateAfter: OK_STATE, sweep: OK_SWEEP,
  droppedBefore: 0, droppedAfter: 0, ...over,
});

test("a turn that survived every renderer channel is reported as surviving", () => {
  const v = survival();
  assert.equal(v.survived, true, v.reasons.join("; "));
  assert.deepEqual(v.reasons, []);
});

test("a release row appearing DURING the sweep fails the verdict, whatever the state says", () => {
  for (const row of [
    { event: "voice_turn_disarmed", turn_id: TURN, source: "electron_main_before_input_event" },
    { event: "voice_turn_reset", turn_id: TURN, source: "node_pty_exit" },
    { event: "voice_turn_cancelled", turn_id: TURN },
  ]) {
    const v = survival({ after: [ARMED_ROW, row] });
    assert.equal(v.survived, false, `${row.event} during the sweep must fail the verdict`);
    assert.match(v.reasons.join(" "), new RegExp(row.event));
  }
});

test("a cancel is exempt ONLY for a turn minted inside the same sweep window", () => {
  // The sweep drives `voice:capture`, the one channel permitted to cancel a turn it minted itself
  // (CHANNEL_MAY_REACH_RELEASE). The first form of this predicate exempted ANY cancel of ANY other
  // turn from ANY source, which is far wider than the audited exception (spec-audit F4).
  const minted = { event: "voice_turn_pending", turn_id: "turn-other" };
  const cancelled = { event: "voice_turn_cancelled", turn_id: "turn-other" };
  assert.equal(survival({ after: [ARMED_ROW, minted, cancelled] }).survived, true,
    "voice:capture voiding a turn it minted in this window is the audited exception");
  const v = survival({ after: [ARMED_ROW, cancelled] });
  assert.equal(v.survived, false,
    "a cancel of a turn that predates the sweep is a release like any other");
  assert.match(v.reasons.join(" "), /voice_turn_cancelled/);
});

test("a window that cannot be trusted to hold every row is a refusal, not a pass", () => {
  // The audit is a bounded ring. At the cap `after.length === before.length`, the tail is empty and
  // the release scan examines nothing — passing in silence, on a ring the least-trusted party can
  // flood (validator MINOR-7 / spec-audit F3). The drop counter is required on both sides.
  assert.equal(survival({ droppedBefore: undefined }).survived, false);
  assert.equal(survival({ droppedAfter: null }).survived, false);
  const dropped = survival({ droppedBefore: 0, droppedAfter: 3 });
  assert.equal(dropped.survived, false);
  assert.match(dropped.reasons.join(" "), /dropped 3 row/);
  // …and a "window" that shrank is not the tail of an append-only trail at all
  assert.equal(survival({ before: [ARMED_ROW, ARMED_ROW], after: [ARMED_ROW] }).survived, false);
});

test("a disarm of some other turn is still a failure — nothing may disarm from a channel", () => {
  const v = survival({
    after: [ARMED_ROW, { event: "voice_turn_disarmed", turn_id: "turn-other", source: "electron_main_operator_chord" }],
  });
  assert.equal(v.survived, false);
});

test("the verdict fails when the turn is no longer held, however the audit reads", () => {
  const cases = [
    { stateAfter: { active: null, turn: { restricted: false, phase: "idle", turn_id: null } } },
    { stateAfter: { active: { turn_id: "turn-other" }, turn: { restricted: true, phase: "active", turn_id: "turn-other" } } },
    { stateAfter: { active: { turn_id: TURN }, turn: { restricted: false, phase: "ended", turn_id: null } } },
    { stateAfter: { active: { turn_id: TURN }, turn: { restricted: true, phase: "pending", turn_id: TURN } } },
  ];
  for (const over of cases) {
    assert.equal(survival(over).survived, false, `expected a failure for ${JSON.stringify(over)}`);
  }
});

test("a sweep that did not cover every channel cannot produce a surviving verdict", () => {
  assert.equal(survival({ sweep: { ok: false, uncovered: ["someNewIntent"], channels: [] } }).survived, false);
  assert.equal(survival({ sweep: { ok: true, channels: [{ method: "input", invoked: false }] } }).survived, false);
  assert.equal(survival({ sweep: null }).survived, false);
});

test("an empty turn id cannot pass — a verdict about no turn is not a verdict", () => {
  assert.equal(survival({ turnId: null }).survived, false);
  assert.equal(survival({ turnId: "" }).survived, false);
});
