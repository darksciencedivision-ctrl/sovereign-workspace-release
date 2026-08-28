"use strict";
/**
 * Hook-dispatch probe (U164): the fold that lets the `.close` receipt MEASURE the voice-turn tool
 * denial instead of waiting for the live model to feel like calling a tool.
 *
 * Layer 1 — a fake spawn pins the parse/timeout/fail-closed contract deterministically.
 * Layer 2 — the REAL host dispatcher runs the REAL pinned hook with no supervisor listening, which
 *           must produce the fail-closed deny. That leg is what proves the wiring exists at all; it
 *           is the same execution the Python profile builder verifies before a launch is authorized.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { EventEmitter } = require("node:events");
const path = require("node:path");
const {
  HOOK_DISPATCH_SHELL, dispatcherCommand, readDecision, dispatchHookEvent,
} = require("../voice/turn-boundary-probe");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const HOOK = path.join(REPO_ROOT, "tools", "live", "voice_turn_boundary.js");
const q = (s) => (/\s/.test(s) ? `"${s}"` : s);
const PINNED_COMMAND = (HOOK_DISPATCH_SHELL === "powershell" ? "& " : "")
  + `${q(process.execPath)} ${q(HOOK)}`;

function fakeSpawn(behaviour) {
  return () => {
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.stdin = { end() {}, on() {} };
    child.kill = () => {};
    setImmediate(() => behaviour(child));
    return child;
  };
}

test("the dispatcher invocation matches the shell the hook command was rendered for", () => {
  const { file, args } = dispatcherCommand("X");
  if (HOOK_DISPATCH_SHELL === "powershell") {
    assert.equal(file, "powershell.exe");
    assert.deepEqual(args, ["-NoProfile", "-NonInteractive", "-Command", "X"]);
  } else {
    assert.equal(file, "sh");
    assert.deepEqual(args, ["-c", "X"]);
  }
});

test("every decision shape the authority emits is read back", () => {
  assert.deepEqual(readDecision(JSON.stringify({ hookSpecificOutput: {
    permissionDecision: "deny", permissionDecisionReason: "why" } })), { decision: "deny", reason: "why" });
  assert.deepEqual(readDecision(JSON.stringify({ hookSpecificOutput: {
    decision: { behavior: "deny", message: "no" } } })), { decision: "deny", reason: "no" });
  assert.deepEqual(readDecision(JSON.stringify({ decision: "block", reason: "r" })),
    { decision: "block", reason: "r" });
  // …and anything unreadable is NOT a denial (the caller must fail closed on the claim)
  assert.deepEqual(readDecision("not json"), { decision: null, reason: null });
  assert.deepEqual(readDecision(JSON.stringify({ ok: true })), { decision: null, reason: null });
});

test("a deny is reported with its exit code and reason", async () => {
  const result = await dispatchHookEvent({
    command: "irrelevant",
    input: { hook_event_name: "PreToolUse" },
    spawn: fakeSpawn((child) => {
      child.stdout.emit("data", JSON.stringify({ hookSpecificOutput: {
        hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: "nope" } }));
      child.emit("exit", 0);
    }),
  });
  assert.equal(result.decision, "deny");
  assert.equal(result.reason, "nope");
  assert.equal(result.exit_code, 0);
});

test("a dispatcher that cannot parse the command yields NO decision, never a denial", async () => {
  const result = await dispatchHookEvent({
    command: "irrelevant",
    input: { hook_event_name: "PreToolUse" },
    spawn: fakeSpawn((child) => {
      child.stderr.emit("data", "At line:1 char:36\nUnexpected token");
      child.emit("exit", 1);
    }),
  });
  // U162 exactly: the shipped receipt read this as "no tool was denied", which is the truth.
  assert.equal(result.decision, null);
  assert.equal(result.exit_code, 1);
  assert.match(result.stderr, /Unexpected token/);
});

test("a hung dispatcher is bounded and reported, and never throws", async () => {
  const result = await dispatchHookEvent({
    command: "irrelevant", input: {}, timeoutMs: 30, spawn: fakeSpawn(() => { /* silence */ }),
  });
  assert.equal(result.decision, null);
  assert.match(result.error, /timed out/);
});

test("a spawn that cannot start is reported, and never throws", async () => {
  const result = await dispatchHookEvent({
    command: "irrelevant", input: {}, spawn: () => { throw new Error("ENOENT"); },
  });
  assert.equal(result.decision, null);
  assert.match(result.error, /ENOENT/);
});

test("LIVE: the real pinned hook, run by the real dispatcher, denies fail-closed", async () => {
  // No supervisor authority in this process's env, so the ONLY honest answer is deny — and the
  // reason must say the authority was unavailable, which is what distinguishes a fail-closed deny
  // from a supervisor decision in the receipt.
  const result = await dispatchHookEvent({
    command: PINNED_COMMAND,
    input: { hook_event_name: "PreToolUse", tool_name: "Bash", session_id: "probe" },
    env: { ...process.env, SOW_VOICE_AUTH_HOST: "", SOW_VOICE_AUTH_PORT: "", SOW_VOICE_AUTH_TOKEN: "" },
  });
  assert.equal(result.exit_code, 0, `dispatcher could not run the pinned hook: ${result.stderr}`);
  assert.equal(result.decision, "deny");
  assert.match(result.reason, /authority unavailable/i);
});
