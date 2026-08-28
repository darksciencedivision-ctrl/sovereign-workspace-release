"use strict";
/**
 * CONDUCTOR **launch-ticket** read-source (Phase 17A `.lease`).
 *
 * The 16C spawn feed (`conductor/spawn-source.js`) proved pane 1 goes through the live-gate chain but
 * deliberately deferred the interactive drive and released its I-X3 terminal before emitting — hence
 * the operator's black pane (F3, `awaiting_live_conductor`). 17A gives the shell something it can
 * actually execute: a governed **launch ticket** from `tools/live/emit_conductor_launch.py`, carrying
 *
 *   * the INTERACTIVE argv (`claude --model <slug>`, never `-p`/`--output-format json`),
 *   * the NAMES of the credential-bearing env vars the shell must drop before spawning (§2.2 — names
 *     only; a value is exactly what this build never transmits),
 *   * the CONDUCTOR chrome + honest selection record, and
 *   * a **durable I-X3 lease that is still held**, owned by THIS process's pid, because the session
 *     the ticket authorizes will outlive the emitter that gated it.
 *
 * The authorization is made Python-side and only read here (invariant 1 / invariant 7: this module
 * holds no authority). Same bounded one-shot `py -3.12` pattern as the picker, the selection badge,
 * the spawn feed and the status bar — not the WS-IPC channel (directive §6 substitution, recorded).
 *
 * FAIL-CLOSED, by contract: a timeout, a non-zero exit, non-JSON output, or a shape drift yields the
 * UNAVAILABLE ticket (`authorized:false`, `node_state:"launch_unavailable"`, no argv, no lease) — the
 * shell keeps the un-launched CONDUCTOR placeholder and says why, rather than spawning a session it
 * cannot prove was authorized (invariant 2: never a naked session). A governed REFUSAL emitted by
 * Python is a well-formed ticket with `refused:true` + `reason` and is surfaced as-is.
 *
 * D-LOOP-1: `releaseConductorLease` is the counterpart the shell MUST call when the session ends (and
 * on quit) so the durable terminal is handed back. `fetchLeaseStatus` is the observable count.
 *
 * Injectable (`spawn`) so the parse/timeout/fail-closed logic is unit-tested with a fake process,
 * with zero dependence on a live host (apps/desktop/test/conductor-launch-source.test.js).
 */
const { spawn: realSpawn, spawnSync: realSpawnSync } = require("child_process");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

class ConductorLaunchSourceError extends Error {}

const LAUNCH_TICKET_SCHEMA = "conductor_launch_ticket@1.0";
const LEASE_RELEASE_SCHEMA = "terminal_lease_release@1.0";
const LEASE_STATUS_SCHEMA = "terminal_lease_status@1.0";
const EMITTER = "tools/live/emit_conductor_launch.py";
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const VOICE_BOUNDARY_SCHEMA = "voice_turn_boundary@1.0";
const VOICE_BOUNDARY_HOOK = "tools/live/voice_turn_boundary.js";
// The shell the vendor CLI's hook dispatcher runs a `command` through on this platform. Must agree
// with node_runtime/supervisor/conductor_permission_profile.dispatch_shell — one rule, two sides.
const HOOK_DISPATCH_SHELL = process.platform === "win32" ? "powershell" : "sh";

// Flags that would make the session HEADLESS (a one-shot worker call, not the operator's chat pane).
// Their presence in a ticket's argv is a producer drift, refused rather than launched (OP-8 §13.1).
const BANNED_FLAGS = ["-p", "--print", "--output-format"];

//: Shell metacharacters. NO argv this build produces contains one — `claude --model <slug>`,
//: `codex -m <slug>`, `ollama run <tag>` are all plain argument vectors. An argument carrying `&&`,
//: `|`, `;`, `<`, `>`, a backtick or `$(` is only useful if something down the line runs it through
//: a shell, and at that point the binary that executes is not the one that was gated.
//: DEFINED HERE and re-exported so the worker contract shares one rule: it lived only in the picker
//: copy, so the CONDUCTOR ticket — the one the operator actually types into — accepted an argv
//: carrying any of them (validator MINOR-4, 2026-07-26). An enumerated DENYLIST, not a proof.
const SHELL_METACHARACTERS = /[&|;`<>\n\r]|\$\(/;

function sha256(data) {
  return crypto.createHash("sha256").update(data).digest("hex");
}

/** Validate the applied permission profile independently of the Python producer's claim. */
function isWellFormedVoiceBoundary(t, launch, identity) {
  const b = t.authority_boundary;
  if (!b || b.schema !== VOICE_BOUNDARY_SCHEMA) return false;
  if (b.supervisor_owned !== true || b.non_executing_voice_turns !== true
      || b.enforced_by_supervisor_process !== false) return false;
  if (b.prompt_marker_format !== "[[SOVEREIGN_VOICE_CHAT_V2:{turn_id_hex32}]] ") return false;
  if (b.permission_profile_id !== identity.permission_profile_id) return false;
  if (b.hook_relative_path !== VOICE_BOUNDARY_HOOK) return false;
  if (typeof b.hook_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(b.hook_sha256)) return false;
  if (typeof b.settings_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(b.settings_sha256)) return false;
  if (typeof b.hook_command !== "string" || !b.hook_command) return false;
  if (typeof b.hook_runtime !== "string" || !path.isAbsolute(b.hook_runtime)) return false;
  if (!["node", "node.exe"].includes(path.basename(b.hook_runtime).toLowerCase())) return false;
  if (!fs.existsSync(b.hook_runtime)) return false;
  const hook = path.resolve(REPO_ROOT, b.hook_relative_path);
  const rel = path.relative(REPO_ROOT, hook);
  if (rel.startsWith("..") || path.isAbsolute(rel)) return false;
  let hookBytes;
  try { hookBytes = fs.readFileSync(hook); } catch { return false; }
  if (sha256(hookBytes) !== b.hook_sha256) return false;
  if (!Array.isArray(b.hook_argv) || b.hook_argv.length !== 2
      || path.resolve(b.hook_argv[0]) !== path.resolve(b.hook_runtime)
      || path.resolve(b.hook_argv[1]) !== hook) return false;
  // `subprocess.list2cmdline` quotes these two paths iff they contain whitespace. Quotes inside a
  // filesystem path are invalid on Windows and refused here rather than imperfectly re-escaped.
  if (b.hook_argv.some((arg) => /"/.test(arg))) return false;
  // …and it must be rendered for the dispatcher THIS host actually has (U162). The vendor CLI runs a
  // hook `command` through the platform shell — PowerShell on Windows — which reads a leading quoted
  // token as an EXPRESSION and refuses the line. A hook that never parses is not a boundary: the CLI
  // reports a non-blocking hook error and runs the tool anyway, so this fails OPEN. Derived here from
  // the argv vector rather than trusted from the producer's own field.
  if (b.hook_command_shell !== HOOK_DISPATCH_SHELL) return false;
  if (b.hook_command_verified !== true) return false;
  const line = b.hook_argv.map((arg) => /\s/.test(arg) ? `"${arg}"` : arg).join(" ");
  const expectedCommand = HOOK_DISPATCH_SHELL === "powershell" ? `& ${line}` : line;
  if (b.hook_command !== expectedCommand) return false;

  const settingsIndexes = [];
  launch.argv.forEach((arg, i) => { if (arg === "--settings") settingsIndexes.push(i); });
  if (settingsIndexes.length !== 1) return false;
  const at = settingsIndexes[0];
  const raw = launch.argv[at + 1];
  if (typeof raw !== "string" || sha256(Buffer.from(raw, "utf8")) !== b.settings_sha256) return false;
  let settings;
  try { settings = JSON.parse(raw); } catch { return false; }
  const hooks = settings && settings.hooks;
  if (!hooks || typeof hooks !== "object") return false;
  for (const event of ["UserPromptSubmit", "PreToolUse", "PermissionRequest",
    "ConfigChange", "Stop", "StopFailure", "SessionEnd"]) {
    const rows = hooks[event];
    if (!Array.isArray(rows) || rows.length !== 1 || !Array.isArray(rows[0].hooks)
        || rows[0].hooks.length !== 1 || rows[0].hooks[0].type !== "command"
        || rows[0].hooks[0].command !== b.hook_command) return false;
  }
  if (hooks.PreToolUse[0].matcher !== ".*" || hooks.PermissionRequest[0].matcher !== ".*") return false;
  return true;
}

function isWellFormedFlagBoundary(t, launch, identity) {
  const b = t.authority_boundary;
  const d = t.conductor_descriptor;
  if (b.schema !== "conductor_permission_boundary@1.0"
      || b.provider !== d.adapter_id || b.permission_profile_id !== identity.permission_profile_id
      || b.supervisor_owned !== true || b.sandbox !== "read-only"
      || b.approval_policy !== "never" || b.automatic_approval !== false
      || b.unrestricted_tools !== false) return false;
  const args = launch.argv || [];
  return args.includes("--sandbox") && args.includes("read-only")
    && args.includes("--config") && args.includes("approval_policy=never")
    && args.includes("-m") && args.includes(d.model_id);
}

/** Containment is selected by the boundary profile the ticket carries, never by a provider name.
 * Each profile has an independent shell-side verifier; an unknown profile fails closed. */
const AUTHORITY_BOUNDARY_PROFILES = Object.freeze({
  [VOICE_BOUNDARY_SCHEMA]: isWellFormedVoiceBoundary,
  "conductor_permission_boundary@1.0": isWellFormedFlagBoundary,
});

function isWellFormedAuthorityBoundary(t, launch, identity) {
  const b = t && t.authority_boundary;
  const d = t && t.conductor_descriptor;
  if (!b) return false;
  // Legacy tickets predate the explicit descriptor; only their pinned hook profile remains valid.
  if (!d) return b.schema === VOICE_BOUNDARY_SCHEMA
    && isWellFormedVoiceBoundary(t, launch, identity);
  if (d.role !== "conductor" || d.registered !== true || d.conductor_capable !== true) return false;
  if (d.permission_profile_id !== identity.permission_profile_id) return false;
  const verify = AUTHORITY_BOUNDARY_PROFILES[b.schema];
  return typeof verify === "function" && verify(t, launch, identity);
}

/** The fail-closed shape when the emitter cannot be reached/parsed. NOT a governed refusal (which
 * Python emits with refused:true): the shell could not obtain an authorization at all. */
function unavailableTicket(reason = "conductor launch ticket unavailable") {
  return {
    schema: LAUNCH_TICKET_SCHEMA,
    authorized: false,
    refused: false,
    reason,
    node_state: "launch_unavailable",
    launch: null,
    chrome: null,
    selection_record: null,
    lease: null,
    release_with: null,
    governor_released: true, // nothing was acquired, so nothing leaked
    gates: null,
  };
}

/** A ticket is usable only if it carries the pinned schema, a boolean `authorized`, and — when it
 * claims authorization — an interactive argv with no headless flag, a scrub-name list, the governed
 * workspace the session must be bound to, the session key its terminal is counted under, and a held
 * durable lease. A refusal must say so with a reason. Anything else is refused (fail closed). */
function isWellFormedTicket(t) {
  if (!t || typeof t !== "object") return false;
  if (t.schema !== LAUNCH_TICKET_SCHEMA) return false;
  if (typeof t.authorized !== "boolean") return false;
  if (!t.authorized) {
    return t.refused === true && typeof t.reason === "string" && t.reason.length > 0;
  }
  const l = t.launch;
  if (!l || typeof l !== "object") return false;
  if (!Array.isArray(l.argv) || l.argv.length === 0) return false;
  if (l.interactive !== true || l.one_shot !== false) return false;
  // Split on `=` first: `--output-format=json` is the SAME flag as `--output-format json`, and the
  // exact match alone was defeated by the `=value` form. The worker contract fixed this in its own
  // copy and left this one — the fix belonged to both (spec-audit MINOR-11, 2026-07-26).
  if (l.argv.some((a) => BANNED_FLAGS.includes(String(a).split("=")[0]))) return false;
  // The `--settings` VALUE is exempt from the metacharacter denylist and only from it: it is the
  // permission-profile JSON, whose every byte is separately pinned below (settings_sha256, one
  // `--settings`, every hook command identical to the boundary's, and that command re-derived here
  // from the hash-pinned hook path). Since U162 it legitimately carries PowerShell's call operator,
  // and a denylist that refuses the profile it is supposed to protect just removes the profile.
  const settingsValueAt = l.argv.indexOf("--settings") + 1;
  const isProfilePayload = (i) => settingsValueAt > 0 && i === settingsValueAt;
  if (l.argv.some((a, i) => !isProfilePayload(i) && SHELL_METACHARACTERS.test(String(a)))) return false;
  if (SHELL_METACHARACTERS.test(String(l.executable || ""))) return false;
  if (!Array.isArray(l.env_scrub_names)) return false;
  // The governed workspace the ConPTY must be bound to (U78(a)): a shell that spawns the session in
  // whatever directory it happened to start in has bound it to nothing. No cwd ⇒ no launch.
  if (typeof l.cwd !== "string" || !l.cwd) return false;
  // The RESOLVED binary the presence gate found. A ConPTY spawn takes a file, not a PATH search, and
  // the shell must execute exactly what was gated — it never resolves a name of its own.
  if (typeof l.executable !== "string" || !l.executable) return false;
  const id = t.identity;
  if (!id || typeof id !== "object") return false;
  if (typeof id.node_id !== "string" || !id.node_id) return false;
  if (typeof id.permission_profile_id !== "string" || !id.permission_profile_id) return false;
  if (!isWellFormedAuthorityBoundary(t, l, id)) return false;
  // The session key the terminal is counted under (U75). Without it the shell cannot tell whether
  // the ticket it is holding authorizes the session it is about to spawn.
  if (typeof id.session_id !== "string" || !id.session_id) return false;
  const lease = t.lease;
  if (!lease || typeof lease !== "object") return false;
  if (typeof lease.lease_id !== "string" || !lease.lease_id) return false;
  if (lease.durable !== true) return false;
  if (lease.session_id !== id.session_id) return false;
  if (!Number.isFinite(lease.in_use) || lease.in_use < 1) return false;
  return !!t.chrome && typeof t.chrome === "object";
}

function isWellFormedRelease(r) {
  return !!r && typeof r === "object" && r.schema === LEASE_RELEASE_SCHEMA
    && typeof r.released === "boolean";
}

function isWellFormedStatus(s) {
  return !!s && typeof s === "object" && s.schema === LEASE_STATUS_SCHEMA
    && !!s.subscriptions && typeof s.subscriptions === "object";
}

/**
 * Run a bounded one-shot Python emitter and return the parsed JSON. STRICT: throws
 * ConductorLaunchSourceError on timeout / non-zero exit / non-JSON / malformed shape.
 *
 * `opts.script` selects the emitter (default: the launch ticket's). Exported as `runPythonEmitter`
 * so the sibling conductor sources use ONE copy of this fail-closed contract rather than each
 * growing its own subtly different spawn/parse/timeout handling.
 *
 * `opts.input` (Phase 17B) is written to the child's stdin and the stream is closed. The worker
 * launch ticket takes its picker selection that way rather than as an argv value: a selection is a
 * nested JSON object, and Windows argv quoting is exactly the class of thing that survives a unit
 * test and mangles a real payload at first launch.
 */
function runEmitter(args, opts, wellFormed, what) {
  const spawn = opts.spawn || realSpawn;
  const python = opts.python || "py";
  const pythonArgs = opts.pythonArgs || ["-3.12"];
  const timeoutMs = opts.timeoutMs || 25000;
  const full = [...pythonArgs, opts.script || EMITTER, ...args];

  return new Promise((resolve, reject) => {
    let child;
    try {
      // `env` omitted ⇒ the child inherits this process's environment (Node's default), which is how
      // every existing caller runs. An explicit `opts.env` is the scratch-ledger override a test or
      // an in-runtime self-check uses so it never touches the operator's real lease file.
      child = spawn(python, full, opts.env ? { cwd: opts.cwd, env: opts.env } : { cwd: opts.cwd });
    } catch (e) {
      reject(new ConductorLaunchSourceError(`could not launch the ${what} emitter: ${e.message}`));
      return;
    }
    let out = "";
    let err = "";
    let settled = false;
    const finish = (fn, arg) => {
      if (settled) return;
      settled = true;
      clearTimeout(to);
      try { child.kill(); } catch { /* gone */ }
      fn(arg);
    };
    const to = setTimeout(
      () => finish(reject, new ConductorLaunchSourceError(`${what} emitter timed out after ${timeoutMs}ms`)),
      timeoutMs,
    );
    if (typeof opts.input === "string") {
      // Deliver the payload and CLOSE stdin — an emitter that reads to EOF would otherwise hang
      // until the timeout. A stdin write can fail if the child died first (EPIPE); that failure is
      // not the outcome, the exit/parse below is, so it is captured rather than thrown.
      try {
        if (child.stdin) {
          child.stdin.on("error", () => { /* child gone; exit handler reports the real reason */ });
          child.stdin.end(opts.input);
        }
      } catch { /* same */ }
    }
    if (child.stdout) child.stdout.on("data", (d) => { out += d.toString(); });
    if (child.stderr) child.stderr.on("data", (d) => { err += d.toString(); });
    child.on("error", (e) => finish(reject, new ConductorLaunchSourceError(`${what} emitter failed to run: ${e.message}`)));
    child.on("exit", (code) => {
      if (code !== 0) {
        finish(reject, new ConductorLaunchSourceError(`${what} emitter exited ${code}${err ? `: ${err.trim().slice(0, 200)}` : ""}`));
        return;
      }
      let parsed;
      try { parsed = JSON.parse(out); }
      catch (e) { finish(reject, new ConductorLaunchSourceError(`${what} emitter emitted non-JSON: ${e.message}`)); return; }
      if (!wellFormed(parsed)) {
        finish(reject, new ConductorLaunchSourceError(`${what} emitter emitted a malformed payload`));
        return;
      }
      finish(resolve, parsed);
    });
  });
}

/**
 * Obtain a governed launch ticket. `holderPid` OWNS the durable lease and MUST be the long-lived
 * process that will hold the session (the Electron main process) — the emitter refuses without it.
 * `sessionId` is the key the terminal is counted under and reclaimed by (U75/U77): the SHELL picks
 * it before asking, so a ticket that never arrives can still be handed back.
 * STRICT (throws); use `sourceConductorLaunchTicket` for the display contract.
 */
function fetchConductorLaunchTicket(opts = {}) {
  const pid = Number(opts.holderPid);
  if (!Number.isInteger(pid) || pid <= 0) {
    return Promise.reject(new ConductorLaunchSourceError(
      "holderPid is required — a durable I-X3 lease must be owned by the process that holds the session"));
  }
  const sessionId = typeof opts.sessionId === "string" ? opts.sessionId.trim() : "";
  if (!sessionId) {
    return Promise.reject(new ConductorLaunchSourceError(
      "sessionId is required — a terminal is counted per SESSION, not per (constant) conductor node id"));
  }
  return runEmitter(["--emit-conductor-launch", "--holder-pid", String(pid),
    "--session-id", sessionId], opts, isWellFormedTicket, "conductor-launch")
    .then((t) => {
      // Fail closed on a ticket for a DIFFERENT session than the one we are about to spawn: it
      // would run under a terminal counted elsewhere, and our reclaim key would free the wrong one.
      if (t.authorized && t.identity && t.identity.session_id !== sessionId) {
        throw new ConductorLaunchSourceError(
          `ticket authorizes session ${t.identity.session_id}, not ${sessionId}`);
      }
      return t;
    });
}

/** DISPLAY contract: NEVER throws. `{ok, ticket, error?}`; `ok:true` only means a well-formed ticket
 * was parsed — read `ticket.authorized` for the governed decision. */
async function sourceConductorLaunchTicket(opts = {}) {
  try {
    return { ok: true, ticket: await fetchConductorLaunchTicket(opts) };
  } catch (e) {
    const error = `${e.name || "Error"}: ${e.message}`;
    return { ok: false, error, ticket: unavailableTicket(error) };
  }
}

/** Hand a durable terminal back (D-LOOP-1). NEVER throws — a failed release is reported, and the
 * ledger reaps a lease whose holder process is gone, so a crash cannot wedge the count either. */
async function releaseConductorLease(leaseId, opts = {}) {
  if (!leaseId) return { ok: false, released: false, error: "no lease id" };
  try {
    const r = await runEmitter(["--release-lease", String(leaseId)], opts, isWellFormedRelease, "lease-release");
    return { ok: true, released: r.released === true, subscriptions: r.subscriptions || {}, error: r.error || null };
  } catch (e) {
    return { ok: false, released: false, error: `${e.name || "Error"}: ${e.message}` };
  }
}

/**
 * Hand back the terminal held by ONE session key (U77). This is the reclaim path when the ticket
 * itself never arrived — a shape refusal or a timeout leaves the lease acquired Python-side with no
 * lease id on this side, and only the session key (chosen here, before asking) can name it.
 * NEVER throws.
 */
async function releaseConductorLeaseSession(sessionId, opts = {}) {
  if (!sessionId) return { ok: false, released: false, error: "no session id" };
  try {
    const r = await runEmitter(["--release-session", String(sessionId)], opts, isWellFormedRelease,
      "lease-release-session");
    return { ok: true, released: r.released === true, count: r.released_count || 0,
      subscriptions: r.subscriptions || {}, error: r.error || null };
  } catch (e) {
    return { ok: false, released: false, error: `${e.name || "Error"}: ${e.message}` };
  }
}

/**
 * BLOCKING release for the quit path. `before-quit` gives no chance to await a promise, and the
 * durable count must not read 1/2 to the next process until the OS reaps this pid. Bounded hard
 * (default 12 s) and never throws — a crash-exit is still covered by dead-holder reaping, so this
 * is an accuracy improvement, not the safety net.
 */
function releaseConductorLeaseSessionSync(sessionId, opts = {}) {
  if (!sessionId) return { ok: false, released: false, error: "no session id" };
  const spawnSync = opts.spawnSync || realSpawnSync;
  const python = opts.python || "py";
  const pythonArgs = opts.pythonArgs || ["-3.12"];
  try {
    const res = spawnSync(python, [...pythonArgs, EMITTER, "--release-session", String(sessionId)],
      { cwd: opts.cwd, timeout: opts.timeoutMs || 12000, encoding: "utf8" });
    if (res.error) return { ok: false, released: false, error: String(res.error.message || res.error) };
    if (res.status !== 0) return { ok: false, released: false, error: `emitter exited ${res.status}` };
    const parsed = JSON.parse(res.stdout);
    if (!isWellFormedRelease(parsed)) return { ok: false, released: false, error: "malformed release payload" };
    return { ok: true, released: parsed.released === true, count: parsed.released_count || 0 };
  } catch (e) {
    return { ok: false, released: false, error: `${e.name || "Error"}: ${e.message}` };
  }
}

/** The observable durable n/allowance count. NEVER throws; fail-closed to an empty, honest view. */
async function fetchLeaseStatus(opts = {}) {
  try {
    const s = await runEmitter(["--emit-lease-status"], opts, isWellFormedStatus, "lease-status");
    return { ok: true, status: s };
  } catch (e) {
    return { ok: false, error: `${e.name || "Error"}: ${e.message}`, status: null };
  }
}

/**
 * The credential classifier, ported from the Python authority
 * `adapters/frontier/provider_cli_common.py` — `PROVIDER_CREDENTIAL_ENV_KEYS`,
 * `CREDENTIAL_KEY_PREFIXES`, `CREDENTIAL_KEY_SUBSTRINGS` and `PRESERVED_PROVIDER_CONFIG_KEYS`.
 *
 * Why a port and not an import: this decision is needed on the Electron main path, which has no
 * Python in it, and the two runtimes cannot import each other. W-32 closed the drift debt the way
 * the operator ruled — by PARITY TESTING rather than a cross-language policy service. The Python
 * classifier remains the semantic AUTHORITY and `tests/unit/test_credential_classifier_parity.py`
 * drives a pinned vector through both, requiring identical verdicts including mixed case. A name
 * that leaves one side and not the other fails there.
 */
const CREDENTIAL_ENV_NAMES = Object.freeze([
  "XAI_API_KEY", "XAI_API_BASE_URL", "GROK_API_KEY",
  "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
  "GOOGLE_CLOUD_PROJECT", "GOOGLE_GENAI_API_KEY", "ANTIGRAVITY_API_KEY",
  // Not credentials, but both redirect or inject into an npm-installed Node CLI: `NODE_OPTIONS` can
  // inject a `--require` module into the child, and `NODE_EXTRA_CA_CERTS` can make an interception
  // proxy's certificate trusted. Neither carries a prefix or substring the nets below catch (U264).
  "NODE_OPTIONS", "NODE_EXTRA_CA_CERTS",
  // W-32: the third member of that family. `NODE_PATH` prepends directories to module resolution,
  // so a `require()` inside an npm-installed Node CLI can be answered by an attacker-chosen file
  // without altering the CLI or its argv at all.
  "NODE_PATH",
]);
const CREDENTIAL_ENV_PREFIXES = Object.freeze(["XAI_", "GROK_", "GEMINI_", "GOOGLE_", "ANTIGRAVITY_"]);
const CREDENTIAL_ENV_SUBSTRINGS = Object.freeze([
  "TOKEN", "SECRET", "API_KEY", "APIKEY", "PASSWORD", "KEY", "AUTH", "CREDENTIAL",
]);
// The ONE exemption, carried over with its evidence: `GROK_SANDBOX` is the env form of the only
// filesystem/network containment lever that CLI documents. A scrubber that removes the sandbox is
// not a safety feature (U265).
const PRESERVED_ENV_NAMES = Object.freeze(["GROK_SANDBOX"]);

/**
 * Fail-closed, case-INSENSITIVE: true if `name` is a known credential/endpoint key, carries a
 * provider prefix, or contains a secret-bearing substring. Deliberately a superset — the dishonest
 * direction is leaving a new key un-scrubbed. Case-insensitive because Windows env names are
 * case-insensitive to the OS while a plain object delete is not, which is the [[U105]] divergence.
 */
function isCredentialEnvName(name) {
  const up = String(name || "").toUpperCase();
  if (PRESERVED_ENV_NAMES.includes(up)) return false;
  if (CREDENTIAL_ENV_NAMES.includes(up)) return true;
  if (CREDENTIAL_ENV_PREFIXES.some((p) => up.startsWith(p))) return true;
  return CREDENTIAL_ENV_SUBSTRINGS.some((tok) => up.includes(tok));
}

/**
 * A child environment with every credential-classified name REMOVED. Pure — the caller passes the
 * base env and it is never mutated. Non-secret vars (PATH, HOME, USERPROFILE, temp, locale) are
 * preserved deliberately: a scrub that empties the environment proves nothing about the scrub, and
 * a pane with no PATH cannot run.
 *
 * This is the DEFAULT-path counterpart to `scrubbedLaunchEnv`. That one drops the names a launch
 * TICKET enumerates; this one applies the classifier where there is no ticket at all — the ordinary
 * operator pane, which until W-29 inherited this shell's entire environment.
 */
function scrubCredentialEnv(baseEnv) {
  const env = { ...(baseEnv || {}) };
  for (const key of Object.keys(env)) {
    if (isCredentialEnvName(key)) delete env[key];
  }
  return env;
}

/**
 * The capabilities the SHELL mints FOR a child during a governed launch. They are exempt from the
 * stage-4 assertion and from nothing else — stage 3 still deletes any INHERITED copy, and the
 * minting step then supplies a fresh value, so an operator-set `SOW_VOICE_AUTH_TOKEN` cannot ride
 * through.
 *
 * An enumerated list, not "whatever the augmenter added". The dynamic form was considered and
 * rejected: it would make stage 4 unable to catch a compromised augmenter injecting a credential,
 * which is a guard that cannot fire — the U367 shape this programme keeps finding. Adding a new
 * shell capability without listing it here fails CLOSED and loudly, which is the right direction.
 *
 * Every name here matches the classifier: `SOVEREIGN_CONTROL_TOKEN` on `TOKEN`, and all four voice
 * names on `AUTH`. That is why the list is needed at all — without it a Claude-hook conductor
 * launch would be refused by its own shell.
 */
const SHELL_MINTED_CAPABILITY_NAMES = Object.freeze([
  "SOVEREIGN_CONTROL_TOKEN",
  "SOW_VOICE_AUTH_HOST", "SOW_VOICE_AUTH_PORT", "SOW_VOICE_AUTH_TOKEN", "SOW_VOICE_AUTH_SCHEMA",
]);

/**
 * STAGE 4 support: every credential-classified name present in `env` that the shell did NOT mint
 * for this launch. Pure, and it reports NAMES only (§2.2) so a refusal can say what is wrong
 * without reproducing a value.
 *
 * Called on the environment ACTUALLY handed to the child — after the minting steps — because stage
 * 3 having run is not the same fact as the child being clean, and the review found that distinction
 * being lost ("measured in the wrong process").
 */
function credentialNamesIn(env) {
  const minted = new Set(SHELL_MINTED_CAPABILITY_NAMES.map((n) => n.toUpperCase()));
  return Object.keys(env || {})
    .filter((k) => isCredentialEnvName(k) && !minted.has(String(k).toUpperCase()));
}

/**
 * STAGE 2 support: the ticket-declared names still present in `env`, compared CASE-INSENSITIVELY.
 *
 * Windows env names are case-insensitive to the OS while a plain-object delete is not — the U105
 * divergence — so an exact-spelling guard would be blind to the class of leak it guards against.
 * This is the conductor path's copy of the rule `worker-spawn.js:299-304` already applies; that
 * inline guard is deliberately left where it is, because it is the guard the fault-injection seam
 * exists to drive and moving it would be a change to working evidence machinery.
 */
function ticketScrubLeftovers(ticketNames, env) {
  const present = new Set(Object.keys(env || {}).map((k) => k.toLowerCase()));
  return (Array.isArray(ticketNames) ? ticketNames : [])
    .filter((n) => present.has(String(n).toLowerCase()));
}

/**
 * The child environment for the authorized launch: this process's env MINUS every name the ticket
 * lists (§2.2). Pure — the caller passes the base env, so the rule is unit-testable and the shell's
 * real `process.env` is never mutated.
 */
function scrubbedLaunchEnv(ticket, baseEnv) {
  const env = { ...(baseEnv || {}) };
  const names = (ticket && ticket.launch && ticket.launch.env_scrub_names) || [];
  for (const n of names) delete env[n];
  return env;
}

module.exports = {
  ConductorLaunchSourceError,
  runPythonEmitter: runEmitter,
  LAUNCH_TICKET_SCHEMA,
  LEASE_RELEASE_SCHEMA,
  LEASE_STATUS_SCHEMA,
  BANNED_FLAGS,
  VOICE_BOUNDARY_SCHEMA, VOICE_BOUNDARY_HOOK, HOOK_DISPATCH_SHELL, isWellFormedVoiceBoundary,
  AUTHORITY_BOUNDARY_PROFILES, isWellFormedFlagBoundary, isWellFormedAuthorityBoundary,
  SHELL_METACHARACTERS,
  fetchConductorLaunchTicket,
  sourceConductorLaunchTicket,
  releaseConductorLease,
  releaseConductorLeaseSession,
  releaseConductorLeaseSessionSync,
  fetchLeaseStatus,
  unavailableTicket,
  isWellFormedTicket,
  scrubbedLaunchEnv,
  CREDENTIAL_ENV_NAMES,
  isCredentialEnvName,
  scrubCredentialEnv,
  SHELL_MINTED_CAPABILITY_NAMES,
  credentialNamesIn,
  ticketScrubLeftovers,
};
