"use strict";
/**
 * Phase 17C `.close-revalidate2`: the non-executing voice-turn decision must live in the
 * long-lived supervisor process. The vendor hook is only a fail-closed transport.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const path = require("node:path");
const net = require("node:net");
const { spawn } = require("node:child_process");

const {
  SupervisorVoiceTurnAuthority,
  requestSupervisor,
  failClosedHookResult,
  OPERATOR_DISARM_SOURCES,
} = require("../voice/turn-authority");
const {
  exactProcessExitResetObserved,
} = require("../selfcheck/voice-conductor-selfcheck");

test("only the exact supervisor-armed prompt can bind a voice turn to a vendor session", () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "a".repeat(64) });
  const armed = authority.arm("ordinary conversation");

  const forged = authority.handle({
    token: authority.token,
    input: {
      hook_event_name: "UserPromptSubmit",
      session_id: "vendor-session",
      prompt: `${armed.prompt_marker}different text`,
    },
  });
  assert.equal(forged.output.decision, "block");
  assert.equal(authority.snapshot().active, null);

  const accepted = authority.handle({
    token: authority.token,
    input: {
      hook_event_name: "UserPromptSubmit",
      session_id: "vendor-session",
      prompt: armed.payload,
    },
  });
  assert.equal(accepted.output.hookSpecificOutput.hookEventName, "UserPromptSubmit");
  assert.equal(authority.snapshot().active.session_id, "vendor-session");
  assert.deepStrictEqual(authority.audit.map((row) => row.event),
    ["voice_turn_pending", "voice_turn_rejected", "voice_turn_armed"]);
});

test("the supervisor denies tools, permission escalation and overlapping typed turns until process exit", () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "b".repeat(64) });
  const armed = authority.arm("use a tool only if permitted");
  authority.handle({
    token: authority.token,
    input: {
      hook_event_name: "UserPromptSubmit",
      session_id: "vendor-session",
      prompt: armed.payload,
    },
  });

  const tool = authority.handle({
    token: authority.token,
    input: { hook_event_name: "PreToolUse", session_id: "vendor-session", tool_name: "Bash" },
  });
  assert.equal(tool.output.hookSpecificOutput.permissionDecision, "deny");

  const permission = authority.handle({
    token: authority.token,
    input: { hook_event_name: "PermissionRequest", session_id: "vendor-session", tool_name: "Bash" },
  });
  assert.equal(permission.output.hookSpecificOutput.decision.behavior, "deny");

  const overlap = authority.handle({
    token: authority.token,
    input: {
      hook_event_name: "UserPromptSubmit",
      session_id: "vendor-session",
      prompt: "operator typed while voice response is still active",
    },
  });
  assert.equal(overlap.output.decision, "block");

  const lifecycle = authority.handle({
    token: authority.token,
    input: { hook_event_name: "StopFailure", session_id: "vendor-session" },
  });
  assert.equal(lifecycle.output, null);
  assert.equal(authority.snapshot().active.session_id, "vendor-session",
    "vendor lifecycle is an observation, never authority to remove the restriction");
  assert.equal(authority.handle({
    token: authority.token,
    input: { hook_event_name: "PreToolUse", session_id: "vendor-session", tool_name: "Read" },
  }).output.hookSpecificOutput.permissionDecision, "deny");
  authority.reset("SessionManager observed the process exit");
  assert.equal(authority.snapshot().active, null);
  assert.equal(authority.audit.at(-1).event, "voice_turn_reset");
});

test("forged lifecycle from the token-holding child cannot create deny-then-allow", () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "4".repeat(64) });
  const armed = authority.arm("ordinary chat");
  authority.handle({
    token: authority.token,
    input: {
      hook_event_name: "UserPromptSubmit",
      session_id: "real-vendor-session",
      prompt: armed.payload,
    },
  });
  for (const event of ["Stop", "StopFailure", "SessionEnd"]) {
    authority.handle({
      token: authority.token,
      input: { hook_event_name: event, session_id: "attacker-chosen-wrong-session" },
    });
    const tool = authority.handle({
      token: authority.token,
      input: { hook_event_name: "PreToolUse", session_id: "real-vendor-session", tool_name: "Bash" },
    });
    assert.equal(tool.output.hookSpecificOutput.permissionDecision, "deny", event);
  }
  assert.equal(authority.snapshot().active.session_id, "real-vendor-session");
});

test("the pinned hook profile cannot be changed out from under a later voice turn", () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "2".repeat(64) });
  const changed = authority.handle({
    token: authority.token,
    input: {
      hook_event_name: "ConfigChange",
      session_id: "vendor-session",
      source: "project_settings",
      file_path: ".claude/settings.json",
    },
  });
  assert.equal(changed.output.decision, "block");
  assert.match(changed.output.reason, /pinned|profile|supervisor/i);
});

test("a cancelled or replaced turn can never be admitted later", () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "c".repeat(64) });
  const first = authority.arm("first");
  assert.throws(() => authority.arm("overlap"), /already pending/i);
  assert.equal(authority.cancel(first.turn_id, "body write failed"), true);
  const stale = authority.handle({
    token: authority.token,
    input: {
      hook_event_name: "UserPromptSubmit",
      session_id: "vendor-session",
      prompt: first.payload,
    },
  });
  assert.equal(stale.output.decision, "block");
});

test("a later voice turn atomically supersedes the restriction without an allow gap", () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "5".repeat(64) });
  const first = authority.arm("first voice turn");
  authority.handle({
    token: authority.token,
    input: {
      hook_event_name: "UserPromptSubmit",
      session_id: "vendor-session",
      prompt: first.payload,
    },
  });
  const second = authority.arm("second voice turn");
  // The first restriction remains active while the second payload is pending.
  assert.equal(authority.snapshot().active.turn_id, first.turn_id);
  assert.equal(authority.snapshot().pending.turn_id, second.turn_id);
  assert.equal(authority.handle({
    token: authority.token,
    input: { hook_event_name: "PreToolUse", session_id: "vendor-session", tool_name: "Bash" },
  }).output.hookSpecificOutput.permissionDecision, "deny");
  authority.handle({
    token: authority.token,
    input: {
      hook_event_name: "UserPromptSubmit",
      session_id: "vendor-session",
      prompt: second.payload,
    },
  });
  assert.equal(authority.snapshot().pending, null);
  assert.equal(authority.snapshot().active.turn_id, second.turn_id);
});

test("wrong-token requests are refused and never mutate supervisor state", () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "d".repeat(64) });
  const armed = authority.arm("hello");
  assert.throws(() => authority.handle({
    token: "e".repeat(64),
    input: {
      hook_event_name: "UserPromptSubmit",
      session_id: "vendor-session",
      prompt: armed.payload,
    },
  }), /authentication/i);
  assert.equal(authority.snapshot().active, null);
  assert.equal(authority.snapshot().pending.turn_id, armed.turn_id);
});

test("the real loopback transport reaches the supervisor process and is torn down", async (t) => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "f".repeat(64) });
  await authority.start();
  t.after(async () => authority.stop());
  const armed = authority.arm("hello over loopback");
  const result = await requestSupervisor({
    env: authority.childEnv({}),
    input: {
      hook_event_name: "UserPromptSubmit",
      session_id: "vendor-session",
      prompt: armed.payload,
    },
    timeoutMs: 1000,
  });
  assert.equal(result.output.hookSpecificOutput.hookEventName, "UserPromptSubmit");
  assert.equal(authority.snapshot().active.session_id, "vendor-session");
  assert.equal(authority.address().address, "127.0.0.1");
  await authority.stop();
  assert.equal(authority.address(), null);
});

test("a client that never sends a newline cannot own voice-authority shutdown", async () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "0".repeat(64) });
  const address = await authority.start();
  const socket = net.connect(address.port, address.address);
  await new Promise((resolve) => { socket.once("connect", resolve); socket.once("error", resolve); });
  const started = Date.now();
  const outcome = await authority.stop({ timeoutMs: 120 });
  assert.ok(Date.now() - started < 1000);
  assert.equal(outcome.closed, true);
  assert.equal(outcome.forced, true);
  assert.equal(outcome.timed_out, false);
  assert.equal(outcome.timeout_ms, 120);
  socket.destroy();
});

test("a ticket is upgraded to supervisor-enforced only while the real service is listening", async (t) => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "1".repeat(64) });
  const ticketBoundary = {
    schema: "voice_turn_boundary@1.0",
    supervisor_owned: true,
    non_executing_voice_turns: true,
    enforced_by_supervisor_process: false,
    hook_sha256: "a".repeat(64),
    settings_sha256: "b".repeat(64),
  };
  assert.equal(authority.runtimeBoundary(ticketBoundary), null);
  await authority.start();
  t.after(async () => authority.stop());
  const runtime = authority.runtimeBoundary(ticketBoundary);
  assert.equal(runtime.enforced_by_supervisor_process, true);
  assert.equal(runtime.broker_schema, "supervisor_voice_turn_authority@1.0");
  assert.equal(Object.prototype.hasOwnProperty.call(runtime, "token"), false);
  await authority.stop();
  assert.equal(authority.runtimeBoundary(ticketBoundary), null);
});

test("the actual pinned hook process transports its decision to Electron main", async (t) => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "3".repeat(64) });
  await authority.start();
  t.after(async () => authority.stop());
  const armed = authority.arm("real hook transport");
  const hook = path.resolve(__dirname, "..", "..", "..", "tools", "live", "voice_turn_boundary.js");
  const result = await new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [hook], {
      cwd: path.resolve(__dirname, "..", "..", ".."),
      env: authority.childEnv(process.env),
      windowsHide: true,
    });
    let out = "";
    let err = "";
    child.stdout.on("data", (chunk) => { out += chunk.toString(); });
    child.stderr.on("data", (chunk) => { err += chunk.toString(); });
    child.on("error", reject);
    child.on("exit", (code) => resolve({ code, out, err }));
    child.stdin.end(JSON.stringify({
      hook_event_name: "UserPromptSubmit",
      session_id: "vendor-session",
      prompt: armed.payload,
    }));
  });
  assert.equal(result.code, 0, result.err);
  assert.equal(JSON.parse(result.out).hookSpecificOutput.hookEventName, "UserPromptSubmit");
  assert.equal(authority.snapshot().active.session_id, "vendor-session");
});

test("transport loss is fail-closed for every authority-bearing hook event", () => {
  const marked = failClosedHookResult("UserPromptSubmit", "supervisor unavailable");
  assert.equal(marked.output.decision, "block");
  const tool = failClosedHookResult("PreToolUse", "supervisor unavailable");
  assert.equal(tool.output.hookSpecificOutput.permissionDecision, "deny");
  const permission = failClosedHookResult("PermissionRequest", "supervisor unavailable");
  assert.equal(permission.output.hookSpecificOutput.decision.behavior, "deny");
  const config = failClosedHookResult("ConfigChange", "supervisor unavailable");
  assert.equal(config.output.decision, "block");
});

test("supervisor reset audit carries the exact PTY generation and pid that authorized release", () => {
  const authority = new SupervisorVoiceTurnAuthority({
    token: "a".repeat(64),
    randomBytes: () => Buffer.alloc(16, 7),
    now: () => "2026-07-28T00:00:00.000Z",
  });
  const armed = authority.arm("ordinary chat");
  authority.handle({
    token: authority.token,
    input: { hook_event_name: "UserPromptSubmit", session_id: "vendor-session", prompt: armed.payload },
  });
  authority.reset("the supervised conductor process exited", {
    source: "node_pty_exit",
    process_exited: true,
    pane_id: "pane-1",
    session_id: "pane-1#4242.1",
    generation: 12,
    pid: 31337,
  });

  const reset = authority.snapshot().audit.find((row) => row.event === "voice_turn_reset");
  assert.deepEqual({
    source: reset.source,
    process_exited: reset.process_exited,
    pane_id: reset.pane_id,
    session_id: reset.session_id,
    generation: reset.generation,
    pid: reset.pid,
  }, {
    source: "node_pty_exit",
    process_exited: true,
    pane_id: "pane-1",
    session_id: "pane-1#4242.1",
    generation: 12,
    pid: 31337,
  });
});

// ---- `.disarm` (U166): an admitted voice turn must END, and only on a signal Electron main
// measures itself. Before this, `_active` cleared only on the observed OS-process exit or an
// undocumented chord, so the FIRST utterance of a session muted the operator's own keyboard
// (`UserPromptSubmit` blocked) and denied every tool for the rest of the session.

test("an admitted voice turn is disarmed by the operator's own keystroke, observed by Electron main", () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "6".repeat(64) });
  const armed = authority.arm("summarize the build status");
  authority.handle({
    token: authority.token,
    input: { hook_event_name: "UserPromptSubmit", session_id: "vendor-session", prompt: armed.payload },
  });
  assert.equal(authority.turnState().restricted, true);
  assert.equal(authority.turnState().phase, "active");

  const row = authority.disarm("electron_main_before_input_event", { key_kind: "printable" });
  assert.equal(row.event, "voice_turn_disarmed");
  assert.equal(row.turn_id, armed.turn_id);
  assert.equal(row.source, "electron_main_before_input_event");
  assert.equal(row.phase, "active");
  // …and it does NOT record which key: an append-only audit of the operator's keystrokes is a keylogger.
  assert.equal(Object.prototype.hasOwnProperty.call(row, "key"), false);
  assert.equal(authority.turnState().restricted, false);

  // the operator's own typed prompt is admitted again — the leg whose absence hid this defect
  const typed = authority.handle({
    token: authority.token,
    input: { hook_event_name: "UserPromptSubmit", session_id: "vendor-session", prompt: "and now I am typing" },
  });
  assert.equal(typed.output, null, "a typed prompt after the disarm must not be blocked");
  // …and ordinary typed tool use is no longer denied by the voice restriction
  assert.equal(authority.handle({
    token: authority.token,
    input: { hook_event_name: "PreToolUse", session_id: "vendor-session", tool_name: "Read" },
  }).output, null);
});

test("a pending turn the operator interrupts is disarmed too, and cannot be admitted afterwards", () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "7".repeat(64) });
  const armed = authority.arm("half-written utterance");
  assert.equal(authority.turnState().phase, "pending");
  const row = authority.disarm("electron_main_operator_chord", { chord: "Ctrl+Shift+Escape" });
  assert.equal(row.phase, "pending");
  assert.equal(authority.handle({
    token: authority.token,
    input: { hook_event_name: "UserPromptSubmit", session_id: "vendor-session", prompt: armed.payload },
  }).output.decision, "block");
});

test("only main-owned operator signals disarm — the vendor's own events and any invented source cannot", () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "8".repeat(64) });
  const armed = authority.arm("ordinary chat");
  authority.handle({
    token: authority.token,
    input: { hook_event_name: "UserPromptSubmit", session_id: "vendor-session", prompt: armed.payload },
  });
  // the child holds the transport bearer, so nothing it can SAY may end the restriction
  for (const event of ["Stop", "StopFailure", "SessionEnd"]) {
    authority.handle({ token: authority.token, input: { hook_event_name: event, session_id: "vendor-session" } });
    assert.equal(authority.turnState().restricted, true, `${event} disarmed the turn`);
  }
  // `electron_main_operator_pane_input` is in this list DELIBERATELY: bytes on the pane:input channel
  // look like the operator typing, but xterm.js also emits onData for terminal replies the pane's own
  // process elicits — so the supervised child could have produced one on demand.
  for (const forged of ["vendor_session_end", "electron_main_operator_pane_input", "", null, undefined, "hook"]) {
    assert.equal(authority.disarm(forged, {}), null, `disarmed on ${JSON.stringify(forged)}`);
    assert.equal(authority.turnState().restricted, true);
  }
  assert.equal(authority.snapshot().audit.filter((r) => r.event === "voice_turn_disarm_refused").length, 6);
  assert.equal(authority.handle({
    token: authority.token,
    input: { hook_event_name: "PreToolUse", session_id: "vendor-session", tool_name: "Bash" },
  }).output.hookSpecificOutput.permissionDecision, "deny");
  // the enumerated sources are exactly the two Electron main observes on the OS input path
  assert.deepEqual(Object.keys(OPERATOR_DISARM_SOURCES).sort(), [
    "electron_main_before_input_event",
    "electron_main_operator_chord",
  ]);
});

test("disarming nothing is not an event, and the restriction state is observable (invariant 27)", () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "9".repeat(64) });
  assert.equal(authority.disarm("electron_main_operator_chord", {}), null);
  assert.deepEqual(authority.snapshot().audit.map((r) => r.event), []);
  const idle = authority.turnState();
  assert.equal(idle.restricted, false);
  assert.equal(idle.phase, "idle");
  assert.equal(idle.turn_id, null);
  const armed = authority.arm("speak");
  authority.handle({
    token: authority.token,
    input: { hook_event_name: "UserPromptSubmit", session_id: "vendor-session", prompt: armed.payload },
  });
  const live = authority.turnState();
  assert.equal(live.restricted, true);
  assert.equal(live.turn_id, armed.turn_id);
  assert.equal(live.session_id, "vendor-session");
  assert.ok(live.since, "an armed turn must carry when it started");
  // the recovery the operator can actually perform has to be NAMED, or the state is not discoverable
  assert.match(live.recovery, /typ(e|ing)/i);
  assert.match(live.recovery, /Ctrl\+Shift\+Escape/);
  // …and it must not scope the bound narrower than the code: any key in this window ends the turn,
  // not only one typed into the conductor pane (spec-audit M-4, U170).
  assert.match(live.recovery, /anywhere in this window/i);
});

test("every turn-state transition notifies the shell so the chrome cannot show a stale restriction", () => {
  const seen = [];
  const authority = new SupervisorVoiceTurnAuthority({
    token: "0".repeat(64),
    onChange: (state) => seen.push(state.phase),
  });
  const armed = authority.arm("speak");
  authority.handle({
    token: authority.token,
    input: { hook_event_name: "UserPromptSubmit", session_id: "vendor-session", prompt: armed.payload },
  });
  authority.disarm("electron_main_before_input_event", { key_kind: "enter" });
  const second = authority.arm("speak again");
  authority.cancel(second.turn_id, "body write failed");
  const third = authority.arm("and again");
  authority.handle({
    token: authority.token,
    input: { hook_event_name: "UserPromptSubmit", session_id: "vendor-session", prompt: third.payload },
  });
  authority.reset("the supervised conductor process exited", { source: "node_pty_exit" });
  // U178 changed two of these, and the change is the point: the operator's keystroke moves an ADMITTED
  // turn to `ended` (their keyboard is back; the answer in flight still cannot use tools) rather than
  // to `idle`, and the cancelled turn that follows falls back to that still-denying state — the first
  // turn's answer does not stop being in flight because a second utterance was abandoned.
  assert.deepEqual(seen, ["pending", "active", "ended", "pending", "ended", "pending", "active", "idle"]);
});

test("the admitted-turn notice tells the model what actually ends the restriction", () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "e".repeat(64) });
  const armed = authority.arm("ordinary chat");
  const admitted = authority.handle({
    token: authority.token,
    input: { hook_event_name: "UserPromptSubmit", session_id: "vendor-session", prompt: armed.payload },
  });
  const context = admitted.output.hookSpecificOutput.additionalContext;
  assert.match(context, /operator/i);
  // "until the turn stops" asserted a disarm the code did not have (spec-audit M4)
  assert.doesNotMatch(context, /until the turn stops/i);
});

// ---------------------------------------------------------------------------------------------
// U178 — the operator's keystroke ends the turn for THEM; it must not hand the in-flight spoken
// turn an execution capability. The model is frequently still generating the answer to the spoken
// prompt at that moment, and before this the deny path simply stopped running (I-V3/invariant 25
// negated). The bound is the operator's NEXT PROMPT, which is a fact the vendor reports but which
// only ARRIVES because the operator typed one — the safe direction if it is ever forged is that a
// forged prompt lifts a restriction the operator had already ended.
// ---------------------------------------------------------------------------------------------

function admit(authority, text = "summarize the build status", sessionId = "vendor-session") {
  const armed = authority.arm(text);
  authority.handle({
    token: authority.token,
    input: { hook_event_name: "UserPromptSubmit", session_id: sessionId, prompt: armed.payload },
  });
  return armed;
}

const preToolUse = (authority, sessionId = "vendor-session") => authority.handle({
  token: authority.token,
  input: { hook_event_name: "PreToolUse", session_id: sessionId, tool_name: "Bash" },
});

const typedPrompt = (authority, sessionId = "vendor-session") => authority.handle({
  token: authority.token,
  input: { hook_event_name: "UserPromptSubmit", session_id: sessionId, prompt: "and now I am typing" },
});

test("after the operator's keystroke the SPOKEN turn's tools stay denied until their next prompt", () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "1".repeat(64) });
  const armed = admit(authority);
  const row = authority.disarm("electron_main_before_input_event", { key_kind: "printable" });
  assert.equal(row.phase, "active");
  // what the disarm bought the OPERATOR: their keyboard, and their own prompts admitted again
  assert.equal(authority.turnState().restricted, false);
  assert.equal(authority.turnState().phase, "ended");
  // …and what it must NOT buy the in-flight answer: tool use
  assert.equal(authority.turnState().tools_denied, true);
  assert.equal(authority.turnState().denying_turn_id, armed.turn_id);
  const denied = preToolUse(authority);
  assert.equal(denied.output.hookSpecificOutput.permissionDecision, "deny",
    "the answer being generated for the spoken prompt executed a tool after the disarm (U178)");
  assert.match(denied.output.hookSpecificOutput.permissionDecisionReason, /voice turn/i);
  assert.equal(authority.handle({
    token: authority.token,
    input: { hook_event_name: "PermissionRequest", session_id: "vendor-session", tool_name: "Bash" },
  }).output.hookSpecificOutput.decision.behavior, "deny");
  const toolRow = authority.snapshot().audit.findLast((r) => r.event === "tool_denied");
  assert.equal(toolRow.turn_id, armed.turn_id);
  assert.equal(toolRow.phase, "ended");

  // THE BOUND: the operator's own next prompt. It is admitted (U166 stands) and it is what releases.
  assert.equal(typedPrompt(authority).output, null, "the operator's own typed prompt must be admitted");
  const released = authority.snapshot().audit.findLast((r) => r.event === "voice_turn_ended_released");
  assert.equal(released.turn_id, armed.turn_id);
  assert.equal(authority.turnState().phase, "idle");
  assert.equal(authority.turnState().tools_denied, false);
  assert.equal(preToolUse(authority).output, null, "ordinary typed tool use stays available after it");
});

test("a turn that never reached the model leaves nothing denying, and a new turn supersedes one that did", () => {
  // A PENDING turn was never admitted: no answer is being generated, so there is nothing in flight
  // to keep denying — and the payload can no longer be admitted at all.
  const pendingOnly = new SupervisorVoiceTurnAuthority({ token: "2".repeat(64) });
  pendingOnly.arm("half-written utterance");
  pendingOnly.disarm("electron_main_operator_chord", { chord: "Ctrl+Shift+Escape" });
  assert.equal(pendingOnly.turnState().phase, "idle");
  assert.equal(pendingOnly.turnState().tools_denied, false);
  assert.equal(preToolUse(pendingOnly).output, null);

  // A NEW spoken turn replaces the ended one: its own restriction is the live one.
  const authority = new SupervisorVoiceTurnAuthority({ token: "3".repeat(64) });
  const first = admit(authority);
  authority.disarm("electron_main_before_input_event", { key_kind: "printable" });
  const second = admit(authority, "and another thing");
  assert.equal(authority.turnState().phase, "active");
  assert.equal(authority.turnState().turn_id, second.turn_id);
  assert.notEqual(second.turn_id, first.turn_id);
  assert.equal(preToolUse(authority).output.hookSpecificOutput.permissionDecision, "deny");
});

test("the observed process exit ends the denial too — the answer it belonged to is gone with it", () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "4".repeat(64) });
  admit(authority);
  authority.disarm("electron_main_before_input_event", { key_kind: "printable" });
  assert.equal(authority.turnState().tools_denied, true);
  authority.reset("the supervised conductor process exited", { source: "node_pty_exit" });
  assert.equal(authority.turnState().phase, "idle");
  assert.equal(authority.turnState().tools_denied, false);
  const row = authority.snapshot().audit.findLast((r) => r.event === "voice_turn_reset");
  assert.equal(row.phase, "ended");
  assert.equal(row.source, "node_pty_exit");
});

// U176 — a release with no provenance row is invisible to the receipt leg that enumerates them.
test("stopping the authority releases what it held, with a main-owned provenance row", async () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "5".repeat(64) });
  await authority.start();
  const armed = admit(authority);
  await authority.stop();
  const row = authority.snapshot().audit.findLast((r) => r.event === "voice_turn_reset");
  assert.equal(row.turn_id, armed.turn_id);
  assert.equal(row.phase, "active");
  assert.equal(row.source, "supervisor_authority_stopped");
  assert.ok(authority.snapshot().audit.some((r) => r.event === "supervisor_authority_stopped"));
});

// U182 — the child holds the bearer and can dispatch hook events at will; every other renderer-facing
// surface in this shell is bounded for exactly that reason.
test("the audit is ring-bounded, and a bounded audit cannot forget what a turn's fate was", () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "6".repeat(64), auditLimit: 50 });
  const armed = admit(authority);
  for (let i = 0; i < 500; i++) preToolUse(authority);
  const snap = authority.snapshot();
  assert.ok(snap.audit.length <= 50, `audit grew to ${snap.audit.length}`);
  assert.ok(snap.audit_dropped > 400, "a bounded audit must say how much it dropped");
  // the fate outlives the row that recorded it — turnFate used to scan the audit for `voice_turn_armed`
  assert.equal(snap.audit.some((r) => r.event === "voice_turn_armed"), false);
  assert.equal(authority.fateOf(armed.turn_id), "vendor_reported_submission");
});

// U180 — admission is the CHILD's claim about itself. The name says so now.
test("the fate a delivery reads is named for what measured it, not for what it hopes", () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "7".repeat(64) });
  const armed = authority.arm("speak");
  assert.equal(authority.fateOf(armed.turn_id), "pending");
  authority.handle({
    token: authority.token,
    input: { hook_event_name: "UserPromptSubmit", session_id: "vendor-session", prompt: armed.payload },
  });
  assert.equal(authority.fateOf(armed.turn_id), "vendor_reported_submission");
  assert.equal(authority.fateOf("never-existed"), "ended");
  authority.disarm("electron_main_before_input_event", { key_kind: "printable" });
  // an admitted turn STAYS a delivery after the operator ends it — it did reach the model
  assert.equal(authority.fateOf(armed.turn_id), "vendor_reported_submission");
  const cancelled = authority.arm("second");
  authority.cancel(cancelled.turn_id, "body write failed");
  assert.equal(authority.fateOf(cancelled.turn_id), "ended_by_cancel");
  const interrupted = authority.arm("third");
  authority.disarm("electron_main_operator_chord", {});
  assert.equal(authority.fateOf(interrupted.turn_id), "ended_by_operator");
  const exited = authority.arm("fourth");
  authority.reset("the supervised conductor process exited", { source: "node_pty_exit" });
  assert.equal(authority.fateOf(exited.turn_id), "ended_by_process_exit");
});

// U183 — `session_id` is taken verbatim from the child; a receipt reads it. Consistency is the
// property that IS checkable here: main mints its own session id in a different namespace from the
// vendor CLI's, so the comparison that can be made is against the id this turn was admitted under.
test("a vendor event carrying a different session id than the turn was admitted under is recorded", () => {
  const authority = new SupervisorVoiceTurnAuthority({ token: "8".repeat(64) });
  const armed = admit(authority, "speak", "vendor-session-A");
  const denied = preToolUse(authority, "vendor-session-B");
  assert.equal(denied.output.hookSpecificOutput.permissionDecision, "deny", "authority is unchanged");
  const row = authority.snapshot().audit.findLast((r) => r.event === "vendor_session_id_mismatch");
  assert.equal(row.turn_id, armed.turn_id);
  assert.equal(row.admitted_session_id, "vendor-session-A");
  assert.equal(row.reported_session_id, "vendor-session-B");
  // …and the matching case records nothing, so the row means something when it appears
  const before = authority.snapshot().audit.length;
  preToolUse(authority, "vendor-session-A");
  assert.equal(authority.snapshot().audit.filter(
    (r) => r.event === "vendor_session_id_mismatch").length, 1);
  assert.ok(authority.snapshot().audit.length > before);
});

// U181 — the hook and the module it requires both live inside the supervised child's writable cwd,
// and were hashed once at launch. Verify at DISPATCH, and fail closed.
test("policy bytes that changed under the running session fail closed on every authority event", () => {
  let verdict = { ok: true };
  const authority = new SupervisorVoiceTurnAuthority({
    token: "9".repeat(64),
    verifyPolicy: () => verdict,
  });
  const armed = authority.arm("speak");
  verdict = { ok: false, reason: "tools/live/voice_turn_boundary.js no longer matches the pinned hash" };
  // admission of the exact armed payload is refused — the transport that would carry it is unpinned
  assert.equal(authority.handle({
    token: authority.token,
    input: { hook_event_name: "UserPromptSubmit", session_id: "vendor-session", prompt: armed.payload },
  }).output.decision, "block");
  assert.equal(preToolUse(authority).output.hookSpecificOutput.permissionDecision, "deny");
  assert.equal(authority.handle({
    token: authority.token,
    input: { hook_event_name: "PermissionRequest", session_id: "vendor-session", tool_name: "Bash" },
  }).output.hookSpecificOutput.decision.behavior, "deny");
  // an ORDINARY typed prompt is blocked too: the boundary's own bytes are unverified, so nothing
  // about this session is trustworthy until it is relaunched
  assert.equal(typedPrompt(authority).output.decision, "block");
  const row = authority.snapshot().audit.findLast((r) => r.event === "policy_bytes_unverified");
  assert.match(row.reason, /pinned hash/);
  // …and a verifier that throws is not a permission either
  const throwing = new SupervisorVoiceTurnAuthority({
    token: "a".repeat(64),
    verifyPolicy: () => { throw new Error("the hook file vanished"); },
  });
  assert.equal(preToolUse(throwing).output.hookSpecificOutput.permissionDecision, "deny");
});

test("the packaged receipt requires exact process identity, not a persuasive reset reason", () => {
  const expected = {
    paneId: "pane-1", sessionId: "pane-1#4242.1", pid: 31337, generation: 12,
  };
  const exact = [{
    event: "voice_turn_reset",
    reason: "the supervised conductor process exited",
    source: "node_pty_exit",
    process_exited: true,
    pane_id: "pane-1",
    session_id: "pane-1#4242.1",
    pid: 31337,
    generation: 12,
  }];
  assert.equal(exactProcessExitResetObserved(exact, expected), true);
  for (const field of ["source", "process_exited", "pane_id", "session_id", "pid", "generation"]) {
    const mutated = { ...exact[0] };
    delete mutated[field];
    assert.equal(exactProcessExitResetObserved([mutated], expected), false,
      `receipt correlation passed without ${field}`);
  }
});
