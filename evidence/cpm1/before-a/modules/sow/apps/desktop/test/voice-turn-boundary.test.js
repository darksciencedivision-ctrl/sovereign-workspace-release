"use strict";
/**
 * The vendor hook is transport only. Authority and turn state live in Electron main's
 * SupervisorVoiceTurnAuthority; a transport fault must become a blocking hook result.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const { handleHookEvent } = require("../../../tools/live/voice_turn_boundary");

test("hook input is forwarded byte-for-byte to the supervisor decision service", async () => {
  const input = {
    hook_event_name: "UserPromptSubmit",
    session_id: "vendor-session",
    prompt: "[[SOVEREIGN_VOICE_CHAT_V2:abc]] ordinary conversation",
  };
  const calls = [];
  const expected = {
    schema: "voice_turn_authority_response@1.0",
    event: "UserPromptSubmit",
    exitCode: 0,
    output: {
      hookSpecificOutput: {
        hookEventName: "UserPromptSubmit",
        additionalContext: "non-executing",
      },
    },
  };
  const result = await handleHookEvent(input, {
    request: async (args) => { calls.push(args); return expected; },
    env: { SENTINEL: "kept-for-injected-request-only" },
  });
  assert.strictEqual(result, expected);
  assert.deepStrictEqual(calls, [{
    input,
    env: { SENTINEL: "kept-for-injected-request-only" },
    timeoutMs: 2000,
  }]);
});

test("transport loss blocks prompt submission", async () => {
  const result = await handleHookEvent({
    hook_event_name: "UserPromptSubmit",
    session_id: "vendor-session",
    prompt: "[[SOVEREIGN_VOICE_CHAT_V2:abc]] hello",
  }, { request: async () => { throw new Error("connection refused"); } });
  assert.equal(result.exitCode, 0);
  assert.equal(result.output.decision, "block");
  assert.match(result.output.reason, /supervisor.*unavailable|connection refused/i);
});

test("transport loss denies tool and permission events", async () => {
  const request = async () => { throw new Error("timeout"); };
  const tool = await handleHookEvent({
    hook_event_name: "PreToolUse", session_id: "vendor-session", tool_name: "Bash",
  }, { request });
  assert.equal(tool.output.hookSpecificOutput.permissionDecision, "deny");

  const permission = await handleHookEvent({
    hook_event_name: "PermissionRequest", session_id: "vendor-session", tool_name: "Bash",
  }, { request });
  assert.equal(permission.output.hookSpecificOutput.decision.behavior, "deny");
});

test("a malformed supervisor response fails closed", async () => {
  const result = await handleHookEvent({
    hook_event_name: "ConfigChange", session_id: "vendor-session",
  }, { request: async () => ({ schema: "wrong", exitCode: 0, output: null }) });
  assert.equal(result.output.decision, "block");
  assert.match(result.output.reason, /malformed/i);
});
