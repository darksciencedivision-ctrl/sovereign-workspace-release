"use strict";
/**
 * Fail-closed transport from the vendor CLI hook dispatcher to Electron main's supervisor-owned
 * voice-turn authority.
 *
 * This process owns no policy and keeps no turn state. It forwards the hook input byte-for-byte to
 * the authenticated loopback service created by the long-lived supervisor process and prints that
 * service's decision. If the service is absent, slow, unauthenticated, or malformed, authority-
 * bearing events block/deny. A hook process therefore cannot authorize a voice turn by itself.
 */
const {
  RESPONSE_SCHEMA,
  requestSupervisor,
  failClosedHookResult,
} = require("../../apps/desktop/voice/turn-authority");

const HOOK_TIMEOUT_MS = 2000;

async function handleHookEvent(input, opts = {}) {
  const event = String(input && input.hook_event_name || "");
  const request = opts.request || requestSupervisor;
  try {
    const result = await request({
      input,
      env: opts.env || process.env,
      timeoutMs: opts.timeoutMs || HOOK_TIMEOUT_MS,
    });
    if (!result || result.schema !== RESPONSE_SCHEMA || result.event !== event
        || !Number.isInteger(result.exitCode)
        || !Object.prototype.hasOwnProperty.call(result, "output")) {
      return failClosedHookResult(event, "supervisor returned a malformed decision");
    }
    return result;
  } catch (e) {
    return failClosedHookResult(event, e && e.message ? e.message : String(e));
  }
}

function cli() {
  let raw = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (chunk) => { raw += chunk; });
  process.stdin.on("end", async () => {
    let result;
    try {
      result = await handleHookEvent(JSON.parse(raw));
    } catch (e) {
      result = failClosedHookResult("", e && e.message ? e.message : String(e));
    }
    if (result.output !== null) process.stdout.write(`${JSON.stringify(result.output)}\n`);
    if (result.error) process.stderr.write(`${result.error}\n`);
    process.exitCode = result.exitCode;
  });
}

if (require.main === module) cli();

module.exports = {
  HOOK_TIMEOUT_MS,
  handleHookEvent,
};
