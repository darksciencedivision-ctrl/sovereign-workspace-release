"use strict";
/**
 * Dispatch ONE hook event through the launch-pinned hook command, exactly as the vendor CLI would.
 *
 * WHY (U162/U164). The voice-turn boundary's claim is "while a voice turn is armed, every tool call
 * is denied before execution". Until now the only way the `.close` receipt could observe that was to
 * hope the live model chose to call a tool during its single answer — a coin flip that, on
 * 2026-07-30, came up tails twice: once because the hook could not be parsed by PowerShell and the
 * vendor's own approval prompt caught the call instead (U162), and once because the model simply
 * answered `65` without touching a tool. A criterion that depends on a model's whim is not a
 * criterion; and the run where it *did* fire was the run where the boundary was broken.
 *
 * So the receipt measures the boundary directly: the SAME pinned `hook_command`, run by the SAME
 * host dispatcher, carrying a real PreToolUse payload, against the SAME authenticated loopback
 * service, while the operator's real voice turn is armed. What that proves is the transport and the
 * decision. What it does NOT prove — and the receipt says so — is that the vendor CLI honours the
 * deny it is handed; that remains the vendor's contract plus U25's OS-level containment.
 *
 * `spawn` is injectable so the parse/timeout/fail-closed fold is unit-tested with no dispatcher.
 */
const { spawn: realSpawn } = require("child_process");

// Must agree with conductor/launch-source.js HOOK_DISPATCH_SHELL and the Python profile builder.
const HOOK_DISPATCH_SHELL = process.platform === "win32" ? "powershell" : "sh";
const DISPATCH_TIMEOUT_MS = 20000;

function dispatcherCommand(command) {
  return HOOK_DISPATCH_SHELL === "powershell"
    ? { file: "powershell.exe", args: ["-NoProfile", "-NonInteractive", "-Command", command] }
    : { file: "sh", args: ["-c", command] };
}

/** The decision a hook result carries, for any of the shapes the authority returns. */
function readDecision(stdout) {
  let parsed;
  try { parsed = JSON.parse(stdout); } catch { return { decision: null, reason: null }; }
  const specific = parsed && parsed.hookSpecificOutput;
  if (specific && typeof specific === "object") {
    if (typeof specific.permissionDecision === "string") {
      return { decision: specific.permissionDecision, reason: specific.permissionDecisionReason || null };
    }
    if (specific.decision && typeof specific.decision === "object") {
      return { decision: specific.decision.behavior || null, reason: specific.decision.message || null };
    }
  }
  if (parsed && typeof parsed.decision === "string") {
    return { decision: parsed.decision, reason: parsed.reason || null };
  }
  return { decision: null, reason: null };
}

/**
 * Run `command` through this host's hook dispatcher with `input` on stdin. NEVER throws: a timeout,
 * a spawn failure or unreadable output is reported as a result with `decision: null`, which every
 * caller must treat as "not denied" (fail closed on the claim, never on the run).
 */
function dispatchHookEvent(opts = {}) {
  const { command, input, env } = opts;
  const spawn = opts.spawn || realSpawn;
  const timeoutMs = opts.timeoutMs || DISPATCH_TIMEOUT_MS;
  const { file, args } = dispatcherCommand(String(command || ""));
  return new Promise((resolve) => {
    let child;
    const done = (extra) => resolve({
      shell: HOOK_DISPATCH_SHELL, command, exit_code: null, stdout: "", stderr: "",
      decision: null, reason: null, ...extra,
    });
    try {
      child = spawn(file, args, { env: env || process.env });
    } catch (e) {
      done({ error: `dispatcher failed to start: ${e && e.message}` });
      return;
    }
    let out = "";
    let err = "";
    let settled = false;
    const finish = (extra) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try { child.kill(); } catch { /* gone */ }
      done(extra);
    };
    const timer = setTimeout(
      () => finish({ stdout: out, stderr: err, error: `dispatch timed out after ${timeoutMs}ms` }),
      timeoutMs);
    if (child.stdout) child.stdout.on("data", (d) => { out += d.toString(); });
    if (child.stderr) child.stderr.on("data", (d) => { err += d.toString(); });
    child.on("error", (e) => finish({ stdout: out, stderr: err, error: `dispatch failed: ${e && e.message}` }));
    if (child.stdin) {
      child.stdin.on("error", () => { /* the exit handler reports the real reason */ });
      try { child.stdin.end(JSON.stringify(input || {})); } catch { /* same */ }
    }
    child.on("exit", (code) => finish({ exit_code: code, stdout: out, stderr: err, ...readDecision(out) }));
  });
}

module.exports = { HOOK_DISPATCH_SHELL, DISPATCH_TIMEOUT_MS, dispatcherCommand, readDecision, dispatchHookEvent };
