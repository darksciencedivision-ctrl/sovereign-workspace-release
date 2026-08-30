"use strict";
const { defaultPython, defaultPythonArgs } = require("../python-runtime");
/**
 * WORKER **launch-ticket** read-source (Phase 17B `.ticket`; closes the read half of U70).
 *
 * 16B's `pane:spawnFromSelection` RECORDED a picker selection and returned a chrome preview — it
 * started nothing, which is what the operator saw: "selecting a model badges the pane but launches
 * nothing" (F3). This module fetches the thing that makes a launch possible: a governed **worker
 * launch ticket** from `tools/live/emit_worker_launch.py`, carrying
 *
 *   * the INTERACTIVE argv + the RESOLVED binary (`claude --model …`, `codex -m … --sandbox …`,
 *     `ollama run <tag>`) and the governed workspace the ConPTY must be bound to,
 *   * the NAMES of the credential-bearing env vars the shell must drop (§2.2 — names only),
 *   * the node identity minted PYTHON-side (the shell never names its own node — invariant 2/29),
 *   * the pane chrome, and
 *   * for a FRONTIER selection, a durable I-X3 lease that is still held; for a LOCAL selection,
 *     `subscription_governed:false` + the residency decision (invariant 19/22 — a local model holds
 *     no subscription terminal and is governed by VRAM instead).
 *
 * The authorization is made Python-side and only READ here (invariant 1: this module holds no
 * authority). Same bounded one-shot `py -3.12` pattern as the picker/status-bar/conductor sources —
 * with the selection delivered on STDIN (a nested object is not something to push through Windows
 * argv quoting).
 *
 * FAIL-CLOSED, by contract: a timeout, a non-zero exit, non-JSON output, or a shape drift yields the
 * UNAVAILABLE ticket (`authorized:false`, `node_state:"launch_unavailable"`, no argv, no lease) — the
 * pane stays un-launched and says why, rather than spawning a session it cannot prove was authorized
 * (invariant 2). A governed REFUSAL emitted by Python is a well-formed ticket with `refused:true` +
 * `reason` and is surfaced as-is.
 *
 * D-LOOP-1: `releaseWorkerTerminal` is the counterpart the shell MUST call when a frontier worker
 * session ends (and on quit) so the durable terminal is handed back.
 *
 * Injectable (`spawn`) so the parse/timeout/fail-closed logic is unit-tested with a fake process,
 * with zero dependence on a live host (apps/desktop/test/worker-launch-source.test.js).
 */
const path = require("path");
const {
  runPythonEmitter, BANNED_FLAGS, SHELL_METACHARACTERS, ConductorLaunchSourceError,
} = require("../conductor/launch-source");

const WORKER_TICKET_SCHEMA = "worker_launch_ticket@1.0";
const LEASE_RELEASE_SCHEMA = "terminal_lease_release@1.0";
const PANE_ATTESTATION_SCHEMA = "worker_pane_spawn_attestation@1.0";
const EMITTER = "tools/live/emit_worker_launch.py";

class WorkerLaunchSourceError extends Error {}

/** The fail-closed shape when the emitter cannot be reached/parsed. NOT a governed refusal (which
 * Python emits with refused:true): the shell could not obtain an authorization at all. */
function unavailableWorkerTicket(reason = "worker launch ticket unavailable") {
  return {
    schema: WORKER_TICKET_SCHEMA,
    authorized: false,
    refused: false,
    reason,
    node_state: "launch_unavailable",
    // The Python producer stamps the gate that refused; there was no gate here, and saying so
    // explicitly keeps the two producers of `worker_launch_ticket@1.0` the same shape — a consumer
    // reading `undefined` cannot tell "no gate ran" from "the field was dropped".
    refused_by: null,
    launch: null,
    chrome: null,
    identity: null,
    containment: null,
    lease: null,
    residency: null,
    subscription_governed: false,
    release_with: null,
    governor_released: true, // nothing was acquired, so nothing leaked
    gates: null,
  };
}

/**
 * The ONE-SHOT (headless) argv shapes of the three CLIs a worker pane can run. `BANNED_FLAGS` alone
 * is claude-specific (`-p`/`--print`/`--output-format`), and 17B added two providers whose headless
 * forms carry no such flag at all: `codex exec …` and `ollama run <tag> "<prompt>"`. A ticket in one
 * of those shapes is a one-shot worker call wearing a pane's clothes — producer drift, refused
 * (spec-audit MINOR-3).
 */
function isHeadlessShape(argv) {
  const rest = argv.slice(1);
  // `exec` ANYWHERE (not merely first): `codex -m <slug> exec "<prompt>"` is the same one-shot call
  // with the flags reordered, and no legitimate interactive argv in this build carries the token.
  if (rest.includes("exec")) return true;
  const positionals = rest.filter((a) => !a.startsWith("-"));
  // `ollama run <tag>` is the interactive session; a THIRD positional is a prompt, i.e. one-shot.
  // Keyed on `run` being PRESENT among the positionals, not on it being first: `ollama --verbose run
  // <tag> "<prompt>"` is the same one-shot call with a flag in front (validator FINDING 8/E1).
  if (positionals.includes("run")) return positionals.length > 2;
  return false;
}

/** A flag matches a banned name whether or not it carries an `=value` (`--output-format=json` is the
 * same flag as `--output-format json`; exact-match alone missed the first form — validator C7/C8). */
function carriesBannedFlag(argv) {
  return argv.some((a) => BANNED_FLAGS.includes(String(a).split("=")[0]));
}

//: adapter → the ONLY executable basename a ticket for that adapter may launch. An ALLOWLIST: the
//: previous denylist ("is it named claude/codex?") was defeated by every wrapper, rename and Win32
//: path form (`cmd /c claude …`, `node …/claude/cli.js`, `run-claude.bat`, 8.3 names, trailing dots)
//: — each of which then read as a local, lease-free, I-X3-uncounted worker (validator FINDING 1).
const ADAPTER_EXECUTABLE = {
  claude_code: "claude",
  openai_codex_cli: "codex",
  grok_build: "grok",
  google_antigravity: "agy",
  ollama_local: "ollama",
};
const FRONTIER_ADAPTERS = ["claude_code", "openai_codex_cli", "grok_build", "google_antigravity"];
//: adapter -> the ONE subscription ref a frontier ticket for it may be counted against. Previously
//: derived as `sub-${adapter}`, which OP-12 §12 broke: the operator named those two resources
//: literally (`grok_build_subscription`, `google_antigravity_subscription`) and the Python governor
//: honours those spellings, so the derived form would have refused every well-formed Grok/Antigravity
//: ticket. Mirrors node_runtime/supervisor/subscription_governor `canonical_subscription_ref` and is
//: pinned to it by tests/unit/test_statusbar_constants_pinned.py — a ref this map gets wrong is a
//: terminal counted in a bucket nothing else reads (the U76 two-bucket defect).
const ADAPTER_SUBSCRIPTION_REF = {
  claude_code: "sub-claude_code",
  openai_codex_cli: "sub-openai_codex_cli",
  grok_build: "grok_build_subscription",
  google_antigravity: "google_antigravity_subscription",
};
//: Tokens that mean "a frontier CLI is being invoked" anywhere in a LOCAL ticket's argv — a local
//: launch has no business naming one, however it is wrapped. The boundary accepts whitespace and
//: quotes as well as path separators: `"… claude"` inside one argument is the same invocation with a
//: space in front of it (validator MINOR-4).
const FRONTIER_TOKENS = /(^|[\\/\s"'])(claude|codex|grok|agy)([-.\s"']|$)/i;
//: The shell-metacharacter rule is DEFINED in the conductor source and imported above, so the two
//: ticket contracts cannot diverge on it again: `>`/`<` were missing from this copy (spec-audit
//: MINOR-12) and the whole rule was missing from the conductor copy - the ticket the operator
//: actually types into (validator MINOR-4). It is an enumerated DENYLIST, not a proof: `%VAR%`,
//: `^` and `@(` are not covered, and a hit yields the generic malformed-ticket refusal rather
//: than a named reason (U103).

//: Forms `launch.executable` may not take AT ALL, checked BEFORE the basename comparison rather than
//: normalised away by it. The normalisation below strips an NTFS alternate-data-stream suffix and
//: trailing space/dot padding so a disguised `claude` is caught — but run in reverse it laundered:
//: `…/ollama.exe:claude.exe` normalised to `ollama` and passed as a lease-free, I-X3-UNCOUNTED local
//: ticket while Win32 executes the STREAM, and FRONTIER_TOKENS never saw it because that rule only
//: scans argv and `:` is not one of its boundaries (round-4 validator MINOR-2, 2026-07-26). No honest
//: producer emits either form — the emitter resolves through `shutil.which` — so on the field that
//: decides what runs they are refused outright. Stripping stays for COMPARISON, where catching a
//: disguise is the whole point. `[A-Za-z]:` at position 1 is a drive letter, not a stream.
//: Stated as the VALID shape and negated, not as the invalid one: written as a positive
//: "…:" match, the optional drive group simply backtracks out of the way and the drive colon of an
//: honest `C:/bin/ollama.exe` satisfies it — every path on this host would have been refused. An
//: extended-length prefix (`\\?\C:\…`) is refused as a side effect; `shutil.which` never returns one.
const STREAM_FREE = /^(?:[A-Za-z]:)?[^:]*$/;
const PADDED_TAIL = /[\s.]$/;

/** Is this executable path one of the forms that would make Win32 run something other than the file
 * the basename names? Surrounding quotes are removed first (they are a quoting artefact, not part of
 * the path); nothing else is normalised, because normalising is precisely what let these through. */
function malformedExecutablePath(value) {
  const v = String(value || "").replace(/^\s*"+/, "").replace(/"+\s*$/, "");
  return !STREAM_FREE.test(v) || PADDED_TAIL.test(v);
}

/** The comparable basename of an executable path: quotes, trailing spaces/dots, NTFS alternate-data
 * streams and the extension removed, lowercased. Normalisation is the point — Win32 resolves
 * `"…\claude.exe "`, `…\claude.exe.` and `…\CLAUDE~1.EXE` to the same binary. */
function executableBasename(value) {
  let v = String(value || "").trim().replace(/^"+|"+$/g, "").replace(/[\s.]+$/g, "");
  const parts = v.split(/[\\/]/);
  let base = parts[parts.length - 1] || "";
  base = base.split(":")[0];                          // strip an ADS suffix (`claude.exe:x`)
  base = base.replace(/\.[a-z0-9]+$/i, "");            // strip the extension
  return base.toLowerCase();
}

/**
 * Does this ticket launch a FRONTIER session? Decided by AGREEMENT between the declared adapter, the
 * declared locality, the presence of a subscription_ref, and — the part that is not a self-report —
 * the binary being launched, which must be the ONE executable that adapter is allowed to run.
 * `null` ⇒ they disagree, or the adapter/binary is not one this build authorizes: drift, refused.
 */
function frontierClaim(t) {
  const chrome = t.chrome || {};
  const id = t.identity || {};
  const launch = t.launch || {};
  const adapter = chrome.adapter;
  const expected = ADAPTER_EXECUTABLE[adapter];
  if (!expected) return null;                         // unknown/absent adapter — never assumed local
  const argv = Array.isArray(launch.argv) ? launch.argv : [];
  // No argument may carry a shell metacharacter — see SHELL_METACHARACTERS.
  if (argv.some((a) => SHELL_METACHARACTERS.test(String(a)))) return null;
  if (SHELL_METACHARACTERS.test(String(launch.executable || ""))) return null;
  // Refused BEFORE the basename comparison — see malformedExecutablePath: the normalisation that
  // catches a disguised frontier binary also laundered one INTO a local ticket.
  if (malformedExecutablePath(launch.executable)) return null;
  // The executable AND argv[0] must BOTH be exactly that adapter's binary — two separate checks
  // because they are two separate facts, and each is load-bearing on its own: `launch.executable` is
  // what the shell actually spawns (so a ticket declaring adapter `ollama_local` while pointing
  // `executable` at `claude.exe` would run an uncounted frontier terminal), while `argv[0]` is what
  // the process sees as its own name. Each has its own test (`worker-launch-source.test.js`) —
  // deleting either line alone used to leave the suite green (validator MAJOR-1).
  if (executableBasename(launch.executable) !== expected) return null;
  if (executableBasename(argv[0]) !== expected) return null;
  const byAdapter = FRONTIER_ADAPTERS.includes(adapter);
  if ((chrome.locality === "frontier") !== byAdapter) return null;
  const ref = typeof id.subscription_ref === "string" ? id.subscription_ref.trim() : "";
  if (!!ref !== byAdapter) return null;               // whitespace-only is not a subscription (C5)
  if (byAdapter && ref !== ADAPTER_SUBSCRIPTION_REF[adapter]) return null;  // the RIGHT one (C9)
  // a LOCAL launch may not name a frontier CLI anywhere in its argv, however it is wrapped
  if (!byAdapter && argv.some((a) => FRONTIER_TOKENS.test(String(a)))) return null;
  return byAdapter;
}

/**
 * A ticket is usable only if it carries the pinned schema, a boolean `authorized`, and — when it
 * claims authorization — an interactive argv with no headless flag, a scrub-name list, the resolved
 * executable, the governed workspace, the Python-minted identity, and the counting fact that matches
 * its locality: a frontier ticket MUST carry a held durable lease for the session asked about; a
 * local ticket MUST carry no lease and a residency decision instead. A refusal must say so with a
 * reason. Anything else is refused (fail closed).
 */
function isWellFormedWorkerTicket(t) {
  if (!t || typeof t !== "object") return false;
  if (t.schema !== WORKER_TICKET_SCHEMA) return false;
  if (typeof t.authorized !== "boolean") return false;
  if (!t.authorized) {
    // A governed refusal must NAME its gate. Without this a producer that dropped `refused_by`
    // stayed "well-formed" and every receipt leg asserting a gate id would silently stop firing —
    // the same disarmed-evidence failure the ids were introduced to fix (spec-audit MINOR-5).
    // `launch_unavailable` is the shell's own no-gate-ran shape (refused:false) and is unaffected.
    // Non-EMPTY: `refused_by: ""` is not naming a gate, and `typeof "" === "string"` let it pass the
    // malformed check while every receipt leg comparing against a gate id would fail — the producer
    // would look well-formed and the evidence would silently stop firing (validator MINOR-3).
    if (t.refused === true && (typeof t.refused_by !== "string" || t.refused_by.trim() === "")) {
      return false;
    }
    return t.refused === true && typeof t.reason === "string" && t.reason.length > 0;
  }
  const l = t.launch;
  if (!l || typeof l !== "object") return false;
  if (!Array.isArray(l.argv) || l.argv.length === 0) return false;
  if (l.interactive !== true || l.one_shot !== false) return false;
  if (carriesBannedFlag(l.argv)) return false;
  if (isHeadlessShape(l.argv)) return false;
  if (!Array.isArray(l.env_scrub_names)) return false;
  if (typeof l.cwd !== "string" || !l.cwd) return false;
  if (typeof l.executable !== "string" || !l.executable) return false;
  const id = t.identity;
  if (!id || typeof id !== "object") return false;
  if (typeof id.node_id !== "string" || !id.node_id) return false;
  if (typeof id.permission_profile_id !== "string" || !id.permission_profile_id) return false;
  if (typeof id.session_id !== "string" || !id.session_id) return false;
  if (typeof id.pane_id !== "string" || !id.pane_id) return false;
  if (!t.chrome || typeof t.chrome !== "object" || t.chrome.governed !== true) return false;
  // WHICH governance applies is NOT taken from any single self-declaration: adapter, locality,
  // subscription_ref and the binary being launched must agree, or the ticket is drift. Otherwise a
  // frontier launch relabelled "local" slips through as an I-X3-uncounted live terminal (invariant
  // 21; gate-validator B2 / FINDING 1).
  const frontier = frontierClaim(t);
  if (frontier === null) return false;
  if (t.subscription_governed !== frontier) return false;
  if (frontier) {
    const lease = t.lease;
    if (!lease || typeof lease !== "object") return false;
    if (typeof lease.lease_id !== "string" || !lease.lease_id) return false;
    if (lease.durable !== true) return false;
    if (lease.session_id !== id.session_id) return false;
    if (lease.subscription_ref !== id.subscription_ref) return false;
    if (!Number.isFinite(lease.in_use) || lease.in_use < 1) return false;
    // the count must be a real one against a real allowance (validator C2)
    if (!Number.isFinite(lease.allowance) || lease.allowance < 1) return false;
    if (lease.in_use > lease.allowance) return false;
    // a frontier ticket has no residency to carry; one that does is drift (validator C3)
    if (t.residency !== null && t.residency !== undefined) return false;
  } else {
    // A local worker holds no subscription terminal — but it must still be governed by SOMETHING,
    // and for a local model that is the residency decision (invariant 22). A ticket with neither a
    // lease nor a residency is an ungoverned launch, refused.
    if (t.lease !== null && t.lease !== undefined) return false;
    if (!t.residency || typeof t.residency !== "object") return false;
  }
  return true;
}

function isWellFormedRelease(r) {
  return !!r && typeof r === "object" && r.schema === LEASE_RELEASE_SCHEMA
    && typeof r.released === "boolean";
}

function isWellFormedAttestation(a) {
  return !!a && typeof a === "object" && a.schema === PANE_ATTESTATION_SCHEMA
    && typeof a.attested === "boolean";
}

/**
 * Obtain a governed worker launch ticket for ONE picker selection.
 * `holderPid` OWNS any durable lease (the Electron main process). `sessionId` is the key the
 * terminal is counted under and reclaimed by; `paneId` is what the node identity is minted from.
 * STRICT (throws); use `sourceWorkerLaunchTicket` for the display contract.
 */
function fetchWorkerLaunchTicket(opts = {}) {
  const pid = Number(opts.holderPid);
  if (!Number.isInteger(pid) || pid <= 0) {
    return Promise.reject(new WorkerLaunchSourceError(
      "holderPid is required — a durable I-X3 lease must be owned by the process that holds the session"));
  }
  const sessionId = typeof opts.sessionId === "string" ? opts.sessionId.trim() : "";
  if (!sessionId) {
    return Promise.reject(new WorkerLaunchSourceError(
      "sessionId is required — a terminal is counted per SESSION, and it is the only reclaim key"));
  }
  const paneId = typeof opts.paneId === "string" ? opts.paneId.trim() : "";
  if (!paneId) {
    return Promise.reject(new WorkerLaunchSourceError(
      "paneId is required — the governed node identity is minted from (pane, role) Python-side"));
  }
  if (!opts.selection || typeof opts.selection !== "object") {
    return Promise.reject(new WorkerLaunchSourceError(
      "selection is required — the picker option the operator chose, carried verbatim"));
  }
  let input;
  try {
    // U105: the scrub list must be classified over the environment the SHELL holds, not only the
    // emitter's. `shellEnvNames` is exactly that — env var NAMES, never values (§2.2), taken from
    // the env this launch will actually be spawned from. The classifier stays the ONE Python rule;
    // the shell contributes nothing but the key spellings it can see and Python cannot.
    // The `=`-filter is not cosmetic: Windows carries hidden per-drive vars named `=C:` / `=ExitCode`
    // in a process environment, and the emitter refuses any entry containing `=` as a name=value pair
    // (its §2.2 tripwire). Dropping them here keeps that tripwire meaningful — none of them can be a
    // credential key under either classifier, so nothing scrubbable is lost.
    const shellEnvNames = Object.keys(opts.shellEnv || {}).filter((n) => n && !n.includes("="));
    input = JSON.stringify({ ...opts.selection, shell_env_names: shellEnvNames });
  } catch (e) {
    return Promise.reject(new WorkerLaunchSourceError(`selection is not serializable: ${e.message}`));
  }
  const args = ["--emit-worker-launch", "--holder-pid", String(pid), "--session-id", sessionId,
    "--pane-id", paneId];
  return runPythonEmitter(args, { ...opts, script: EMITTER, input }, isWellFormedWorkerTicket,
    "worker-launch")
    .then((t) => {
      // Fail closed on a ticket for a DIFFERENT session or pane than the one we are about to spawn:
      // it would run under a terminal counted elsewhere, and our reclaim key would free the wrong one.
      if (t.authorized && t.identity) {
        if (t.identity.session_id !== sessionId) {
          throw new WorkerLaunchSourceError(
            `ticket authorizes session ${t.identity.session_id}, not ${sessionId}`);
        }
        if (t.identity.pane_id !== paneId) {
          throw new WorkerLaunchSourceError(
            `ticket authorizes pane ${t.identity.pane_id}, not ${paneId}`);
        }
      }
      // …and for a workspace this shell did not ask about. The shape contract requires `launch.cwd`
      // to be a non-empty string and nothing more, so "the ConPTY is bound to the governed
      // workspace" rested entirely on the producer plus one in-runtime assertion in the self-check
      // (spec-audit MINOR-8). The shell knows exactly one governed workspace — the root it invoked
      // the emitter from — and a ticket naming a different directory is drift, not a launch: it
      // would put a live model process's working directory outside what was authorized.
      if (t.authorized && opts.cwd) {
        const asked = path.resolve(String(opts.cwd));
        const given = path.resolve(String((t.launch && t.launch.cwd) || ""));
        // Case-insensitively on Windows ONLY, where the filesystem itself is: a case difference
        // there is the same directory, and refusing it would be a false alarm rather than a guard.
        const same = process.platform === "win32"
          ? asked.toLowerCase() === given.toLowerCase() : asked === given;
        if (!same) {
          throw new WorkerLaunchSourceError(
            `ticket binds the session to workspace ${given}, not the governed workspace ${asked}`);
        }
      }
      return t;
    });
}

/** DISPLAY contract: NEVER throws. `{ok, ticket, error?}`; `ok:true` only means a well-formed ticket
 * was parsed — read `ticket.authorized` for the governed decision. */
async function sourceWorkerLaunchTicket(opts = {}) {
  try {
    return { ok: true, ticket: await fetchWorkerLaunchTicket(opts) };
  } catch (e) {
    const error = `${e.name || "Error"}: ${e.message}`;
    return { ok: false, error, ticket: unavailableWorkerTicket(error) };
  }
}

/**
 * Hand back the durable terminal held by ONE worker session, on whichever subscription holds it
 * (D-LOOP-1). Safe to call for a LOCAL worker too — it simply reclaims nothing. NEVER throws: a
 * failed release is reported, and the ledger reaps a lease whose holder process is gone, so a crash
 * cannot wedge the count either.
 */
async function releaseWorkerTerminal(sessionId, opts = {}) {
  if (!sessionId) return { ok: false, released: false, error: "no session id" };
  try {
    const r = await runPythonEmitter(["--release-session", String(sessionId)],
      { ...opts, script: EMITTER }, isWellFormedRelease, "worker-lease-release");
    return { ok: true, released: r.released === true, count: r.released_count || 0,
      subscriptions: r.subscriptions || {},
      // The SAME call closes the session's Sovereign node record (18E `.live.electron.wiring`),
      // and the producer reports whether it did. Dropping it here left the shell unable to say
      // whether the pane's record was closed or left open — a measured fact thrown away, which is
      // the shape of the finding the wiring unit's own reviewers raised about `node_registration`.
      nodeRecord: (r.node_record && typeof r.node_record === "object") ? r.node_record : null,
      error: r.error || null };
  } catch (e) {
    return { ok: false, released: false, nodeRecord: null,
      error: `${e.name || "Error"}: ${e.message}` };
  }
}

/**
 * Attest that the pane's supervised ConPTY is ALIVE under `pid`, moving its Sovereign node record
 * from `SPAWNING` to `READY` (18E `.live.electron.wiring`; directive §17.2(1) — a supervised pane
 * as a REGISTERED node).
 *
 * Why a second call rather than a field on the ticket: at ticket time the process does not exist.
 * The record written then says `SPAWNING`, which is the truth — authorized, not yet born — and only
 * the shell can report the moment that stops being true, because only the shell spawns it. The pid
 * is the whole content of the attestation.
 *
 * NEVER throws and NEVER blocks a launch. A bookkeeping fault must not tear down a governed session
 * that is running correctly; the outcome is returned so the caller can record it honestly, and a
 * pane whose attestation failed is a pane with a `SPAWNING` record, which the release still closes.
 */
async function attestWorkerPaneSpawned(nodeKey, sessionId, pid, opts = {}) {
  if (!nodeKey) return { ok: false, attested: false, error: "no node key" };
  // The SESSION, not just the pane: a pane id is reused across sessions, so an attestation keyed
  // on the pane alone can put a live pid onto a stale record a crashed shell left open.
  if (!sessionId) return { ok: false, attested: false, error: "no session id" };
  if (!Number.isInteger(pid) || pid <= 0) {
    return { ok: false, attested: false, error: `no supervised pid to attest (${pid})` };
  }
  try {
    const a = await runPythonEmitter(
      ["--record-pane-spawned", String(nodeKey), "--session-id", String(sessionId),
        "--pid", String(pid)],
      { ...opts, script: EMITTER }, isWellFormedAttestation, "worker-pane-attestation");
    return { ok: true, attested: a.attested === true, state: a.state || null,
      logPath: a.log_path || null,
      incarnation: a.incarnation ?? null, error: a.error || null };
  } catch (e) {
    return { ok: false, attested: false, error: `${e.name || "Error"}: ${e.message}` };
  }
}

/**
 * The BLOCKING release, for `before-quit` — which cannot await (Phase 17B `.spawn`, D-LOOP-1). Same
 * emitter, same reclaim key, hard-bounded. A hard crash is still covered by the ledger's dead-holder
 * reaping, so this is accuracy for the next process to read the count, not the safety net.
 * Mirrors `releaseConductorLeaseSessionSync`; kept beside its async twin so the two cannot drift.
 */
function releaseWorkerTerminalSync(sessionId, opts = {}) {
  if (!sessionId) return { ok: false, released: false, error: "no session id" };
  const spawnSync = opts.spawnSync || require("child_process").spawnSync;
  const python = opts.python || defaultPython();
  const pythonArgs = opts.pythonArgs || defaultPythonArgs();
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

module.exports = {
  WorkerLaunchSourceError,
  ConductorLaunchSourceError,   // what runPythonEmitter throws — re-exported for callers that catch
  WORKER_TICKET_SCHEMA,
  PANE_ATTESTATION_SCHEMA,
  BANNED_FLAGS,
  // Exported for the 18C acceptance verdict, which must read the SAME bucket the launcher counts a
  // terminal in. Re-typing these four strings anywhere else is how the U76 two-bucket defect
  // (a lease written to one ref and read from another) comes back.
  ADAPTER_SUBSCRIPTION_REF,
  // …and for the same reason, the executable ALLOWLIST: 18E's live acceptance verifies "the exact
  // provider" by comparing the binary that was actually spawned against this map. A second literal
  // elsewhere is a provider verified against a binary this contract would refuse.
  ADAPTER_EXECUTABLE,
  fetchWorkerLaunchTicket,
  sourceWorkerLaunchTicket,
  releaseWorkerTerminal,
  releaseWorkerTerminalSync,
  attestWorkerPaneSpawned,
  unavailableWorkerTicket,
  isWellFormedWorkerTicket,
  isWellFormedAttestation,
};
