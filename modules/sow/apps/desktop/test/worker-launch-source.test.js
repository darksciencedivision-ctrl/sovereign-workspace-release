"use strict";
/**
 * WORKER launch-ticket SOURCE tests (Phase 17B `.ticket`) — the glue that turns the Python governed
 * worker emitter (`tools/live/emit_worker_launch.py`) into something the shell can EXECUTE in a
 * pane's ConPTY: a frontier worker with a durable I-X3 lease, or a local worker with a residency
 * decision and deliberately NO lease.
 *
 * Two layers, mirroring conductor-launch-source.test.js:
 *   (1) unit — a FAKE spawn proves the parse + stdin delivery + timeout + fail-closed fold
 *       deterministically: an authorized frontier ticket, an authorized LOCAL ticket, a governed
 *       refusal, a HEADLESS-argv drift (refused), a frontier ticket with no held lease (refused — an
 *       uncounted live terminal defeats I-X3), a LOCAL ticket carrying a lease or missing its
 *       residency (refused — a locality/governance mismatch is producer drift), a ticket for the
 *       WRONG session or pane (refused — our reclaim key would free someone else's terminal),
 *       missing holderPid/sessionId/paneId/selection, non-zero exit, non-JSON, timeout, spawn error;
 *   (2) live integration — the REAL `py -3.12` emitter is invoked against a SCRATCH lease ledger with
 *       this test process's pid as the holder, and the terminal is RELEASED in the same test
 *       (D-LOOP-1). On a host without authorization/CLI the ticket is an honest refusal — also a
 *       pass, never a fabricated launch. Skips without py.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { EventEmitter } = require("node:events");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {
  WorkerLaunchSourceError, WORKER_TICKET_SCHEMA,
  fetchWorkerLaunchTicket, sourceWorkerLaunchTicket, releaseWorkerTerminal, releaseWorkerTerminalSync,
  unavailableWorkerTicket, isWellFormedWorkerTicket, attestWorkerPaneSpawned,
} = require("../picker/launch-source");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const HAVE_PY = spawnSync("py", ["-3.12", "--version"], { encoding: "utf8" }).status === 0;

const SESSION = "pane-2#77.1";
const PANE = "pane-2";

const FRONTIER_SELECTION = {
  option: {
    provider: "claude_code", adapter: "claude_code", locality: "frontier",
    subscription_backed: true, label: "Fable 5", model_slug: "fable-5", verified: false,
    is_fallback: false, roles: ["conductor", "reasoning", "coding"], residency: null,
    available: true, unavailable_reason: null,
  },
  role: "reasoning",
  mode: "autonomous",
};

const LOCAL_SELECTION = {
  option: {
    provider: "ollama_local", adapter: "ollama_local", locality: "local",
    subscription_backed: false, label: "qwen3:8b", model_slug: "qwen3:8b", verified: true,
    is_fallback: false, roles: ["reasoning", "coding"], residency: "not_loaded",
    available: true, unavailable_reason: null,
  },
  role: "reasoning",
  mode: "attended",
};

const FRONTIER_TICKET = {
  schema: WORKER_TICKET_SCHEMA,
  authorized: true,
  refused: false,
  reason: null,
  node_state: "launch_authorized",
  launch: {
    argv: ["claude", "--model", "claude-fable-5"],
    executable: "C:/bin/claude.EXE",
    // the GOVERNED workspace, and it must be the one the caller asked from: the shape contract
    // accepted any non-empty string, so "the ConPTY is bound to the governed workspace" rested on
    // the producer alone (spec-audit MINOR-8). A fixture naming some other directory is now drift.
    cwd: REPO_ROOT,
    interactive: true,
    one_shot: false,
    env_credential_scrubbed: true,
    env_scrub_names: ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"],
    session_id: SESSION,
  },
  chrome: { provider: "claude_code", adapter: "claude_code", locality: "frontier",
    model_label: "Fable 5", governed: true, interactive: true, role: "reasoning",
    // NOT "ready": a frontier authorization has spawned nothing, and the producer no longer emits
    // it (worker_pane_spawn._AUTHORIZED_NOT_STARTED). A fixture the producer cannot emit is the
    // drift this suite exists to catch (validator MINOR-3, 2026-07-26).
    mode: "autonomous", node_state: "launch_authorized" },
  identity: {
    node_id: "worker-pane-2", permission_profile_id: "pp-worker-reasoning",
    subscription_ref: "sub-claude_code", session_id: SESSION, pane_id: PANE,
    workspace: REPO_ROOT, role: "reasoning", mode: "autonomous",
  },
  containment: { authorized: true, supervisor_bound: false, os_job_object: false, owed_to: "U25" },
  lease: {
    lease_id: "lease-w1", subscription_ref: "sub-claude_code", provider: "claude_code",
    node_id: "worker-pane-2", session_id: SESSION, holder_pid: 77,
    durable: true, in_use: 1, allowance: 2, seeded_from_ledger: [],
  },
  residency: null,
  subscription_governed: true,
  model_probe: { label: "fable-5", model: "claude-fable-5", model_available: true, source: "probe-ledger" },
  release_with: ["--release-session", SESSION],
  governor_released: true,
  gates: { live_operation_authorized: true, operator_terms_confirmed: true, cli_present: true,
    ix3_counted: true },
};

const LOCAL_TICKET = {
  ...FRONTIER_TICKET,
  launch: { ...FRONTIER_TICKET.launch, argv: ["C:/bin/ollama.EXE", "run", "qwen3:8b"],
    executable: "C:/bin/ollama.EXE" },
  chrome: { provider: "ollama_local", adapter: "ollama_local", locality: "local",
    model_label: "qwen3:8b", governed: true, interactive: true, role: "reasoning",
    mode: "attended", node_state: "loading" },
  identity: { ...FRONTIER_TICKET.identity, subscription_ref: null },
  lease: null,
  subscription_governed: false,
  residency: { model: "qwen3:8b", scheduled: true, status: "loading", evicted: [] },
  model_probe: null,
  release_with: null,
};

const REFUSAL = {
  schema: WORKER_TICKET_SCHEMA,
  authorized: false,
  refused: true,
  reason: "SpawnRefused: option claude_code/Fable 5 is unavailable (not authorized) — fail closed",
  refused_by: "selection_guard",
  node_state: "launch_refused",
  launch: null, chrome: null, identity: null, lease: null, residency: null,
  subscription_governed: false, release_with: null, governor_released: true, gates: {},
};

function fakeSpawn({ stdout = "", stderr = "", code = 0, neverExit = false, throwOnSpawn = false,
  emitError = null } = {}) {
  const calls = [];
  const spawn = (cmd, args, opts) => {
    const call = { cmd, args, opts, stdin: "" };
    calls.push(call);
    if (throwOnSpawn) throw new Error("ENOENT");
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.stdin = Object.assign(new EventEmitter(), {
      end: (data) => { call.stdin += data == null ? "" : String(data); call.stdinClosed = true; },
    });
    child.kill = () => { child.killed = true; };
    child.killed = false;
    setImmediate(() => {
      if (emitError) { child.emit("error", new Error(emitError)); return; }
      if (stdout) child.stdout.emit("data", Buffer.from(stdout));
      if (stderr) child.stderr.emit("data", Buffer.from(stderr));
      if (!neverExit) child.emit("exit", code);
    });
    return child;
  };
  spawn.calls = calls;
  return spawn;
}

const ask = (spawn, over = {}) => fetchWorkerLaunchTicket({
  spawn, cwd: REPO_ROOT, holderPid: 77, sessionId: SESSION, paneId: PANE,
  selection: FRONTIER_SELECTION, ...over,
});

// ---- (1) unit: fake spawn ---------------------------------------------------
test("an authorized frontier ticket is parsed and the selection is delivered on STDIN", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(FRONTIER_TICKET) });
  const t = await ask(spawn);
  assert.equal(t.authorized, true);
  assert.equal(t.lease.lease_id, "lease-w1");
  assert.deepEqual(spawn.calls[0].args.slice(-7),
    ["tools/live/emit_worker_launch.py", "--emit-worker-launch", "--holder-pid", "77",
      "--session-id", SESSION, "--pane-id", PANE].slice(-7));
  // the picker option travels verbatim on stdin (never through argv quoting), and stdin is CLOSED.
  // Phase 17B `.spawn` adds ONE field beside it: `shell_env_names`, the env var NAMES this shell
  // holds, so the credential-scrub list is classified over the environment the child is actually
  // born into rather than the emitter's (U105). Names only — §2.2 is unchanged, and the emitter
  // refuses any entry carrying a value.
  assert.deepEqual(JSON.parse(spawn.calls[0].stdin), { ...FRONTIER_SELECTION, shell_env_names: [] });
  assert.equal(spawn.calls[0].stdinClosed, true);
  assert.equal(spawn.calls[0].opts.cwd, REPO_ROOT);
});

test("the shell's own env var NAMES ride along, and only names (U105, §2.2)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(FRONTIER_TICKET) });
  await ask(spawn, { shellEnv: { PATH: "C:/bin", ANTHROPIC_API_KEY: "sk-must-not-travel", "=C:": "x" } });
  const sent = JSON.parse(spawn.calls[0].stdin);
  assert.deepEqual(sent.shell_env_names, ["PATH", "ANTHROPIC_API_KEY"]);
  assert.equal(spawn.calls[0].stdin.includes("sk-must-not-travel"), false,
    "a VALUE must never cross to the emitter — the whole point of sending names");
  // Windows carries hidden `=C:`-style vars; the emitter refuses any entry containing `=` as a
  // name=value pair, so they are dropped here rather than tripping that rule on every launch.
  assert.equal(sent.shell_env_names.includes("=C:"), false);
});

test("an authorized LOCAL ticket needs no lease but must carry a residency decision", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(LOCAL_TICKET) });
  const t = await ask(spawn, { selection: LOCAL_SELECTION });
  assert.equal(t.authorized, true);
  assert.equal(t.lease, null);
  assert.equal(t.subscription_governed, false);
  assert.equal(t.residency.status, "loading");

  // …but a local ticket with NEITHER a lease NOR a residency is an ungoverned launch — refused
  assert.equal(isWellFormedWorkerTicket({ ...LOCAL_TICKET, residency: null }), false);
  // …and one that smuggles a lease while claiming to be ungoverned is producer drift — refused
  assert.equal(isWellFormedWorkerTicket({ ...LOCAL_TICKET, lease: FRONTIER_TICKET.lease }), false);
});

test("a governed refusal is surfaced as-is (authorized:false + reason), never a launch", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(REFUSAL) });
  const t = await ask(spawn);
  assert.equal(t.authorized, false);
  assert.equal(t.launch, null);
  assert.match(t.reason, /unavailable/);
});

test("a governed refusal that does not NAME its gate is malformed", async () => {
  // The receipt's fail-closed legs assert `refused_by`. A producer that dropped the field would
  // leave every one of them comparing against `undefined` — green by never firing, which is the
  // disarmed-evidence failure the gate ids were introduced to fix (spec-audit MINOR-5).
  const nameless = { ...REFUSAL };
  delete nameless.refused_by;
  await assert.rejects(() => ask(fakeSpawn({ stdout: JSON.stringify(nameless) })),
    (e) => /malformed/.test(e.message));
  await assert.rejects(() => ask(fakeSpawn({ stdout: JSON.stringify({ ...REFUSAL, refused_by: null }) })),
    (e) => /malformed/.test(e.message));
  // the shell's OWN no-gate-ran shape is unaffected: it sets `refused:false` (it is not a governed
  // refusal at all) and carries `refused_by: null` explicitly, so the two producers agree on shape.
  assert.equal(unavailableWorkerTicket("emitter unreachable").refused_by, null);
  assert.equal(unavailableWorkerTicket("emitter unreachable").refused, false);
});

test("a HEADLESS argv is refused — a worker PANE is never a one-shot worker call", async () => {
  const drift = { ...FRONTIER_TICKET,
    launch: { ...FRONTIER_TICKET.launch, argv: ["claude", "-p", "hi"] } };
  await assert.rejects(() => ask(fakeSpawn({ stdout: JSON.stringify(drift) })),
    (e) => /malformed/.test(e.message));
});

test("a frontier ticket with no HELD lease is refused (an uncounted terminal defeats I-X3)", () => {
  assert.equal(isWellFormedWorkerTicket({ ...FRONTIER_TICKET, lease: null }), false);
  assert.equal(isWellFormedWorkerTicket({
    ...FRONTIER_TICKET, lease: { ...FRONTIER_TICKET.lease, in_use: 0 } }), false);
  assert.equal(isWellFormedWorkerTicket({
    ...FRONTIER_TICKET, lease: { ...FRONTIER_TICKET.lease, durable: false } }), false);
  // a lease counted under a DIFFERENT session than the ticket authorizes
  assert.equal(isWellFormedWorkerTicket({
    ...FRONTIER_TICKET, lease: { ...FRONTIER_TICKET.lease, session_id: "someone-else" } }), false);
});

test("the LOCALITY decides which governance is required — not the ticket's claim about itself", () => {
  // gate-validator B2: a frontier launch that declares itself ungoverned and carries a residency
  // object would otherwise pass as well-formed — an I-X3-uncounted live terminal (invariant 21).
  const uncountedFrontier = { ...FRONTIER_TICKET, lease: null, subscription_governed: false,
    residency: { model: "x", scheduled: true, status: "loading" } };
  assert.equal(isWellFormedWorkerTicket(uncountedFrontier), false);
  // …and a local ticket that claims to be subscription-governed is equally drifted
  assert.equal(isWellFormedWorkerTicket({ ...LOCAL_TICKET, subscription_governed: true }), false);
  // chrome locality and the identity's subscription_ref must agree with each other
  assert.equal(isWellFormedWorkerTicket({
    ...FRONTIER_TICKET, identity: { ...FRONTIER_TICKET.identity, subscription_ref: null } }), false);
  assert.equal(isWellFormedWorkerTicket({
    ...LOCAL_TICKET, chrome: { ...LOCAL_TICKET.chrome, locality: "frontier" } }), false);
  // a lease counted against a DIFFERENT subscription than the identity names
  assert.equal(isWellFormedWorkerTicket({
    ...FRONTIER_TICKET, lease: { ...FRONTIER_TICKET.lease, subscription_ref: "sub-openai" } }), false);
});

test("a wrapped/renamed frontier binary cannot pass itself off as a local worker", () => {
  // The gate-validator defeated the previous denylist ("is it named claude/codex?") with wrappers,
  // renames and Win32 path forms — each then read as a local, lease-free, I-X3-UNCOUNTED worker
  // (FINDING 1). The guard is now an ALLOWLIST: an `ollama_local` ticket must launch `ollama`, and
  // its argv may not name a frontier CLI at all.
  const asLocal = (launch) => ({ ...LOCAL_TICKET, launch: { ...LOCAL_TICKET.launch, ...launch } });
  const disguises = [
    { executable: "C:/Windows/System32/cmd.exe", argv: ["cmd", "/c", "claude", "--model", "x"] },
    { executable: "node", argv: ["node", "C:/u/.local/lib/claude/cli.js"] },
    { executable: "powershell.exe", argv: ["powershell.exe", "-NoProfile", "-Command", "claude"] },
    { executable: "C:/tmp/claude-cli.exe", argv: ["claude-cli"] },
    { executable: "C:/bin/claude.EXE ", argv: ["claude "] },          // trailing space
    { executable: "C:/bin/claude.exe.", argv: ["claude."] },          // trailing dot
    { executable: "\"C:/bin/claude.exe\"", argv: ["claude"] },          // quoted
    { executable: "C:/bin/claude.exe:x", argv: ["claude"] },          // NTFS ADS suffix
    { executable: "C:/shim/run-claude.bat", argv: ["run-claude.bat"] },
  ];
  for (const d of disguises) {
    assert.equal(isWellFormedWorkerTicket(asLocal(d)), false,
      `a local ticket launching ${d.executable} must be refused`);
  }
  // and the honest local control still passes
  assert.equal(isWellFormedWorkerTicket(LOCAL_TICKET), true);
});

test("the basename NORMALISATION cannot be run in reverse to launder a frontier name", () => {
  // The round-4 validator found the inverse of FINDING 1: `executableBasename` strips an NTFS
  // alternate-data-stream suffix and trailing space/dot padding so a disguised CLAUDE is caught —
  // but that same stripping made `…/ollama.exe:claude.exe` normalise to `ollama` and be ACCEPTED as
  // a lease-free, I-X3-uncounted LOCAL ticket, while Win32 would execute the stream. FRONTIER_TOKENS
  // never saw it because it only scanned argv, and `:` is not one of its boundary characters.
  //
  // Padding and streams are now REFUSED OUTRIGHT on `launch.executable` rather than normalised away:
  // no honest producer emits either (the emitter resolves through shutil.which), so the only thing
  // the normalisation was buying on this field was the laundering. Stripping stays for COMPARISON,
  // where catching a disguise is the point.
  const asLocal = (launch) => ({ ...LOCAL_TICKET, launch: { ...LOCAL_TICKET.launch, ...launch } });
  const laundered = [
    { executable: "C:/ol/ollama.exe:claude.exe", argv: ["ollama", "run", "qwen3:8b"] },  // ADS
    { executable: "C:/ol/ollama.exe:codex", argv: ["ollama", "run", "qwen3:8b"] },       // ADS
    { executable: "C:/ol/ollama.exe ", argv: ["ollama", "run", "qwen3:8b"] },            // pad
    { executable: "C:/ol/ollama.exe.", argv: ["ollama", "run", "qwen3:8b"] },            // pad
  ];
  for (const d of laundered) {
    assert.equal(isWellFormedWorkerTicket(asLocal(d)), false,
      `a local ticket whose executable is ${JSON.stringify(d.executable)} must be refused`);
  }
  // the same padding on the FRONTIER side is refused too — the field must be what was gated
  assert.equal(isWellFormedWorkerTicket({ ...FRONTIER_TICKET,
    launch: { ...FRONTIER_TICKET.launch, executable: "C:/bin/claude.exe:ollama" } }), false);
  // NOT refused, deliberately: a directory component named `claude` on the path to a binary whose
  // basename must still be exactly `ollama` cannot make a frontier CLI run, so refusing it would buy
  // nothing and cost an honest host an opaque refusal (the U103 class). The rule stays targeted at
  // the forms that change WHAT EXECUTES.
  assert.equal(isWellFormedWorkerTicket(asLocal({ executable: "C:/claude/ollama.exe" })), true);
  // controls: the honest forms of both localities still pass, so none of the above is vacuous
  assert.equal(isWellFormedWorkerTicket(LOCAL_TICKET), true);
  assert.equal(isWellFormedWorkerTicket(FRONTIER_TICKET), true);
});

test("`launch.executable` is checked SEPARATELY from argv[0] — each on its own", () => {
  // Both checks existed, but the suite only asserted that at LEAST ONE of them did: deleting either
  // line alone left 19/19 green, and with the `executable` line gone a ticket declaring
  // `ollama_local` while pointing `executable` at claude.exe was ACCEPTED as a lease-free,
  // I-X3-uncounted worker — on the field the shell actually spawns (validator MAJOR-1).
  //
  // They are two different facts: `launch.executable` is the binary that RUNS; `argv[0]` is only the
  // name that binary sees for itself. Each disagreement below flips exactly one of them, so each
  // test fails if its own line is removed.
  const execOnly = { ...LOCAL_TICKET,
    launch: { ...LOCAL_TICKET.launch, executable: "C:/bin/claude.EXE", argv: ["ollama", "run", "qwen3:8b"] } };
  assert.equal(isWellFormedWorkerTicket(execOnly), false,
    "the spawned binary is claude while argv[0] says ollama — refused on `executable`");

  const argvOnly = { ...LOCAL_TICKET,
    launch: { ...LOCAL_TICKET.launch, executable: "C:/bin/ollama.EXE", argv: ["claude", "--model", "x"] } };
  assert.equal(isWellFormedWorkerTicket(argvOnly), false,
    "argv[0] names a frontier CLI while `executable` says ollama — refused on argv[0]");

  // the same pair on the frontier side, where the mismatch would spawn something the gate never saw
  assert.equal(isWellFormedWorkerTicket({ ...FRONTIER_TICKET,
    launch: { ...FRONTIER_TICKET.launch, executable: "C:/bin/ollama.exe" } }), false);
  assert.equal(isWellFormedWorkerTicket({ ...FRONTIER_TICKET,
    launch: { ...FRONTIER_TICKET.launch, argv: ["ollama", "--model", "claude-fable-5"] } }), false);

  // …and the honest controls, where the two agree
  assert.equal(isWellFormedWorkerTicket(LOCAL_TICKET), true);
  assert.equal(isWellFormedWorkerTicket(FRONTIER_TICKET), true);
});

test("no argument may carry a shell metacharacter, on either locality", () => {
  // `["ollama","run","x && claude"]` passed every check: the frontier-token boundary required a path
  // separator or start-of-string, so a space in front of `claude` defeated it (validator MINOR-4).
  // Harmless while nothing spawns; a live hazard the moment anything runs an argv through a shell,
  // because at that point the binary allowlist is describing a different program than the one that
  // executes. Refused by class, not by instance.
  const local = (argv) => ({ ...LOCAL_TICKET, launch: { ...LOCAL_TICKET.launch, argv } });
  for (const argv of [["ollama", "run", "x && claude"], ["ollama", "run", "x; claude"],
    ["ollama", "run", "x | claude"], ["ollama", "run", "x`claude`"],
    ["ollama", "run", "x$(claude)"], ["ollama", "run", "x\nclaude"]]) {
    assert.equal(isWellFormedWorkerTicket(local(argv)), false, JSON.stringify(argv));
  }
  assert.equal(isWellFormedWorkerTicket({ ...FRONTIER_TICKET,
    launch: { ...FRONTIER_TICKET.launch, argv: ["claude", "--model", "x && rm"] } }), false);
  // …and on the executable itself. These two forms pass the basename allowlist — `executableBasename`
  // trims and takes the last path segment, so both resolve to "ollama" — and are caught only by the
  // metacharacter check, which is why it is a separate line.
  assert.equal(isWellFormedWorkerTicket({ ...LOCAL_TICKET,
    launch: { ...LOCAL_TICKET.launch, executable: "C:/bin\n/ollama.exe" } }), false);
  assert.equal(isWellFormedWorkerTicket({ ...LOCAL_TICKET,
    launch: { ...LOCAL_TICKET.launch, executable: "C:/bin/ollama.exe && claude" } }), false);
  // a model tag with a colon is NOT a metacharacter — the honest control still passes
  assert.equal(isWellFormedWorkerTicket(LOCAL_TICKET), true);
});

test("a frontier CLI named inside one argument of a LOCAL ticket is still refused", () => {
  const local = (argv) => ({ ...LOCAL_TICKET, launch: { ...LOCAL_TICKET.launch, argv } });
  assert.equal(isWellFormedWorkerTicket(local(["ollama", "run", "start claude"])), false);
  assert.equal(isWellFormedWorkerTicket(local(["ollama", "run", "\"codex\""])), false);
  assert.equal(isWellFormedWorkerTicket(LOCAL_TICKET), true);
});

test("a missing/unknown adapter is never assumed local, and the count must match the adapter", () => {
  const noAdapter = { ...LOCAL_TICKET, chrome: { ...LOCAL_TICKET.chrome, adapter: undefined } };
  assert.equal(isWellFormedWorkerTicket(noAdapter), false);
  const unknown = { ...LOCAL_TICKET, chrome: { ...LOCAL_TICKET.chrome, adapter: "kimi_cloud" } };
  assert.equal(isWellFormedWorkerTicket(unknown), false);
  // capitalised locality is not "frontier"
  assert.equal(isWellFormedWorkerTicket({
    ...FRONTIER_TICKET, chrome: { ...FRONTIER_TICKET.chrome, locality: "Frontier" } }), false);
  // a whitespace-only subscription_ref is not a subscription
  assert.equal(isWellFormedWorkerTicket({
    ...FRONTIER_TICKET, identity: { ...FRONTIER_TICKET.identity, subscription_ref: "   " },
    lease: { ...FRONTIER_TICKET.lease, subscription_ref: "   " } }), false);
  // counted against the WRONG subscription for the adapter
  assert.equal(isWellFormedWorkerTicket({
    ...FRONTIER_TICKET, chrome: { ...FRONTIER_TICKET.chrome, adapter: "openai_codex_cli" } }), false);
});

test("an absurd or unbounded lease count, and a frontier ticket carrying a residency, are refused", () => {
  assert.equal(isWellFormedWorkerTicket({
    ...FRONTIER_TICKET, lease: { ...FRONTIER_TICKET.lease, in_use: Number.MAX_SAFE_INTEGER } }), false);
  assert.equal(isWellFormedWorkerTicket({
    ...FRONTIER_TICKET, lease: { ...FRONTIER_TICKET.lease, allowance: 0 } }), false);
  assert.equal(isWellFormedWorkerTicket({
    ...FRONTIER_TICKET, residency: { model: "smuggled" } }), false);
});

test("a banned flag is banned in its `=value` form too", () => {
  for (const argv of [["claude", "--print=json"], ["claude", "-p=hi"],
    ["claude", "--output-format=stream-json"]]) {
    assert.equal(isWellFormedWorkerTicket({
      ...FRONTIER_TICKET, launch: { ...FRONTIER_TICKET.launch, argv } }), false, argv.join(" "));
  }
});

test("a frontier launch relabelled LOCAL is refused — every self-declaration must agree", () => {
  // validator FINDING 1: reading locality alone let a one-field lie move a claude launch into the
  // branch with no I-X3 requirement. Adapter, locality, subscription_ref and the BINARY must agree.
  const localityLie = {
    ...FRONTIER_TICKET,
    chrome: { ...FRONTIER_TICKET.chrome, locality: "local" },   // adapter/argv still claude
    identity: { ...FRONTIER_TICKET.identity, subscription_ref: null },
    lease: null, subscription_governed: false,
    residency: { model: "claude-fable-5", scheduled: true, status: "loading" },
  };
  assert.equal(isWellFormedWorkerTicket(localityLie), false);
  // the same lie told consistently in the metadata still fails on the BINARY being a frontier CLI
  const fullLie = { ...localityLie, chrome: { ...localityLie.chrome, adapter: "ollama_local" } };
  assert.equal(isWellFormedWorkerTicket(fullLie), false);
  // and the mirror image: a local binary dressed as a counted frontier session
  const inverseLie = { ...LOCAL_TICKET, subscription_governed: true,
    chrome: { ...LOCAL_TICKET.chrome, locality: "frontier", adapter: "claude_code" },
    identity: { ...LOCAL_TICKET.identity, subscription_ref: "sub-claude_code" },
    lease: FRONTIER_TICKET.lease, residency: null };
  assert.equal(isWellFormedWorkerTicket(inverseLie), false);
});

test("the ONE-SHOT argv shapes of all three CLIs are refused, not just claude's flags", () => {
  const codexExec = { ...FRONTIER_TICKET,
    launch: { ...FRONTIER_TICKET.launch, argv: ["codex", "exec", "-m", "gpt-5.5", "do a thing"] } };
  assert.equal(isWellFormedWorkerTicket(codexExec), false);
  // validator FINDING 2: the same call with the flags first is the same one-shot call
  const codexExecReordered = { ...FRONTIER_TICKET,
    launch: { ...FRONTIER_TICKET.launch, executable: "C:/bin/codex.CMD",
      argv: ["codex", "-m", "gpt-5.5", "exec", "do a thing"] },
    chrome: { ...FRONTIER_TICKET.chrome, adapter: "openai_codex_cli" },
    identity: { ...FRONTIER_TICKET.identity, subscription_ref: "sub-openai_codex_cli" },
    lease: { ...FRONTIER_TICKET.lease, subscription_ref: "sub-openai_codex_cli" } };
  assert.equal(isWellFormedWorkerTicket(codexExecReordered), false);
  const ollamaOneShot = { ...LOCAL_TICKET,
    launch: { ...LOCAL_TICKET.launch, argv: ["ollama", "run", "qwen3:8b", "summarize this"] } };
  assert.equal(isWellFormedWorkerTicket(ollamaOneShot), false);
  // …and with a flag in front of `run`, which the positional rule used to miss (FINDING 8/E1)
  assert.equal(isWellFormedWorkerTicket({ ...LOCAL_TICKET,
    launch: { ...LOCAL_TICKET.launch,
      argv: ["ollama", "--verbose", "run", "qwen3:8b", "summarize this"] } }), false);
  // the interactive forms still pass
  assert.equal(isWellFormedWorkerTicket(LOCAL_TICKET), true);
  assert.equal(isWellFormedWorkerTicket(FRONTIER_TICKET), true);
});

test("a ticket without the Python-minted identity is refused (the shell never names its node)", () => {
  assert.equal(isWellFormedWorkerTicket({ ...FRONTIER_TICKET, identity: null }), false);
  assert.equal(isWellFormedWorkerTicket({
    ...FRONTIER_TICKET, identity: { ...FRONTIER_TICKET.identity, permission_profile_id: "" } }), false);
  assert.equal(isWellFormedWorkerTicket({
    ...FRONTIER_TICKET, chrome: { ...FRONTIER_TICKET.chrome, governed: false } }), false);
});

test("a ticket for a different session or pane is refused (our reclaim key frees the wrong one)", async () => {
  const otherSession = { ...FRONTIER_TICKET,
    identity: { ...FRONTIER_TICKET.identity, session_id: "pane-2#77.9" },
    lease: { ...FRONTIER_TICKET.lease, session_id: "pane-2#77.9" } };
  await assert.rejects(() => ask(fakeSpawn({ stdout: JSON.stringify(otherSession) })),
    (e) => /authorizes session/.test(e.message));
  const otherPane = { ...FRONTIER_TICKET,
    identity: { ...FRONTIER_TICKET.identity, pane_id: "pane-9" } };
  await assert.rejects(() => ask(fakeSpawn({ stdout: JSON.stringify(otherPane) })),
    (e) => /authorizes pane/.test(e.message));
});

test("a ticket binding the session to a DIFFERENT workspace is refused (spec-audit MINOR-8)", async () => {
  // The shape contract only ever required `launch.cwd` to be a non-empty string, so the claim "the
  // ConPTY is bound to the governed workspace" rested entirely on the producer plus one in-runtime
  // assertion. The shell knows exactly one governed workspace — the root it invoked the emitter
  // from — and a live model process started somewhere else is outside what was authorized.
  const elsewhere = { ...FRONTIER_TICKET,
    launch: { ...FRONTIER_TICKET.launch, cwd: "C:/Users/Public" } };
  await assert.rejects(() => ask(fakeSpawn({ stdout: JSON.stringify(elsewhere) })),
    (e) => /binds the session to workspace .*, not the governed workspace/.test(e.message));
});

test("…but a mere CASE difference on Windows is the same directory, not drift", async () => {
  const cased = { ...FRONTIER_TICKET,
    launch: { ...FRONTIER_TICKET.launch, cwd: REPO_ROOT.toUpperCase() } };
  const call = () => ask(fakeSpawn({ stdout: JSON.stringify(cased) }));
  if (process.platform === "win32") {
    const t = await call();
    assert.equal(t.authorized, true, "a case-different path on a case-insensitive filesystem is the same workspace");
  } else {
    await assert.rejects(call, (e) => /not the governed workspace/.test(e.message));
  }
});

test("a REFUSED ticket carries no launch at all, and the workspace check does not invent one", async () => {
  const t = await ask(fakeSpawn({ stdout: JSON.stringify(REFUSAL) }));
  assert.equal(t.authorized, false);
  assert.equal(t.refused_by, "selection_guard");
});

test("the request refuses without a holder pid, session id, pane id or selection", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(FRONTIER_TICKET) });
  for (const over of [{ holderPid: 0 }, { sessionId: "" }, { paneId: "" }, { selection: null }]) {
    await assert.rejects(() => ask(spawn, over), (e) => e instanceof WorkerLaunchSourceError);
  }
  assert.equal(spawn.calls.length, 0, "no emitter run without a complete governed request");
});

test("a non-zero exit, non-JSON, a timeout and a spawn failure all fail closed", async () => {
  await assert.rejects(() => ask(fakeSpawn({ stderr: "--pane-id required", code: 2 })),
    (e) => /exited 2/.test(e.message) && /pane-id/.test(e.message));
  await assert.rejects(() => ask(fakeSpawn({ stdout: "totally not json" })),
    (e) => /non-JSON/.test(e.message));
  await assert.rejects(() => ask(fakeSpawn({ neverExit: true }), { timeoutMs: 25 }),
    (e) => /timed out/.test(e.message));
  await assert.rejects(() => ask(fakeSpawn({ throwOnSpawn: true })),
    (e) => /could not launch/.test(e.message));
  await assert.rejects(() => ask(fakeSpawn({ emitError: "boom" })),
    (e) => /failed to run/.test(e.message));
});

test("sourceWorkerLaunchTicket never throws and yields the unavailable ticket on failure", async () => {
  const res = await sourceWorkerLaunchTicket({
    spawn: fakeSpawn({ stdout: "nope" }), cwd: REPO_ROOT, holderPid: 77, sessionId: SESSION,
    paneId: PANE, selection: FRONTIER_SELECTION });
  assert.equal(res.ok, false);
  assert.equal(res.ticket.authorized, false);
  assert.equal(res.ticket.node_state, "launch_unavailable");
  assert.equal(res.ticket.launch, null);
  assert.deepEqual(unavailableWorkerTicket("x").lease, null);
});

test("releaseWorkerTerminal never throws and reports an unreachable emitter honestly", async () => {
  const bad = await releaseWorkerTerminal(SESSION, { spawn: fakeSpawn({ code: 3 }), cwd: REPO_ROOT });
  assert.equal(bad.ok, false);
  assert.equal(bad.released, false);
  assert.equal(bad.nodeRecord, null);
  const none = await releaseWorkerTerminal("", {});
  assert.equal(none.released, false);
});

test("releaseWorkerTerminal surfaces the node record the SAME call closed (18E)", async () => {
  // The emitter closes the session's Sovereign node record on the release call and reports the
  // outcome. Dropping it here left the shell unable to say whether a pane's record was closed or
  // left open — a measured fact discarded, which is the finding the wiring unit's reviewers raised
  // about `node_registration` one layer up.
  const payload = JSON.stringify({
    schema: "terminal_lease_release@1.0", released: true, released_count: 1, subscriptions: {},
    node_record: { closed: true, node_key: "worker-pane-2", incarnation: 1,
      log_path: "C:/store/nodes/node_events.jsonl" },
  });
  const ok = await releaseWorkerTerminal(SESSION, {
    spawn: fakeSpawn({ stdout: payload }), cwd: REPO_ROOT,
  });
  assert.equal(ok.ok, true);
  assert.equal(ok.released, true);
  assert.equal(ok.nodeRecord.closed, true);
  assert.equal(ok.nodeRecord.node_key, "worker-pane-2");
  // …and a producer that reports no node half at all yields null, never a fabricated success.
  const silent = await releaseWorkerTerminal(SESSION, {
    spawn: fakeSpawn({ stdout: JSON.stringify({ schema: "terminal_lease_release@1.0",
      released: true, released_count: 1 }) }),
    cwd: REPO_ROOT,
  });
  assert.equal(silent.nodeRecord, null);
});

// ---- (2) live integration: the REAL emitter, scratch ledger, released in-test ----
test("the real emitter answers a picker selection with a governed ticket (and the terminal is handed back)",
  { skip: !HAVE_PY ? "py -3.12 not available" : false }, async () => {
    const scratch = path.join(os.tmpdir(), `sow-worker-lease-${process.pid}.json`);
    const env = { ...process.env, SOW_TERMINAL_LEASE_LEDGER: scratch };
    const sessionId = `worker-launch-source-test#${process.pid}`;
    try {
      const res = await sourceWorkerLaunchTicket({
        cwd: REPO_ROOT, holderPid: process.pid, sessionId, paneId: "pane-test",
        selection: FRONTIER_SELECTION, timeoutMs: 60000, env,
      });
      assert.equal(res.ok, true, `emitter unreachable: ${res.error}`);
      const t = res.ticket;
      assert.equal(t.schema, WORKER_TICKET_SCHEMA);
      assert.equal(typeof t.authorized, "boolean");
      if (t.authorized) {
        assert.equal(t.launch.one_shot, false);
        assert.equal(t.identity.node_id, "worker-pane-test");
        assert.equal(t.lease.holder_pid, process.pid);
      } else {
        assert.ok(t.reason && t.reason.length > 0, "a refusal must say why");
        assert.equal(t.launch, null);
      }
    } finally {
      // D-LOOP-1 — hand back whatever the run took, then remove the scratch ledger.
      await releaseWorkerTerminal(sessionId, { cwd: REPO_ROOT, timeoutMs: 60000, env });
      try { fs.rmSync(scratch, { force: true }); } catch { /* nothing to remove */ }
    }
  });

// ---- EPC-04: the OpenCode coding ticket ----
// `ADAPTER_EXECUTABLE` is an ALLOWLIST, so adding a provider to it widens what this shell will
// spawn. These tests hold the new entry to the same terms as every other one: it launches ONE
// binary, it is local, it carries no subscription, and it cannot be used to launch anything else.

const OPENCODE_TICKET = {
  ...LOCAL_TICKET,
  launch: { ...LOCAL_TICKET.launch,
    argv: ["C:/npm/opencode.CMD", "C:/repo/worktrees/coding-1", "--pure", "-m",
           "ollama/qwen2.5-coder:3b"],
    executable: "C:/npm/opencode.CMD" },
  chrome: { ...LOCAL_TICKET.chrome, provider: "opencode_local", adapter: "opencode_local",
    model_label: "qwen2.5-coder:3b", role: "coding" },
  residency: { model: "qwen2.5-coder:3b", scheduled: true, status: "loading", evicted: [] },
};

test("an OpenCode coding ticket is accepted as a LOCAL launch", () => {
  // the npm shim spelling `opencode.CMD` must pass: `executableBasename` lowercases and strips the
  // extension, and on Windows this IS how the binary resolves (`shutil.which` returns the .CMD).
  assert.equal(isWellFormedWorkerTicket(OPENCODE_TICKET), true);
});

test("an OpenCode ticket that declares a subscription_ref is refused", () => {
  // invariant 19: a coding pane holds no subscription terminal, so a ref is producer drift.
  const t = { ...OPENCODE_TICKET,
    identity: { ...OPENCODE_TICKET.identity, subscription_ref: "sub-claude_code" } };
  assert.equal(isWellFormedWorkerTicket(t), false);
});

test("an OpenCode ticket that declares frontier locality is refused", () => {
  const t = { ...OPENCODE_TICKET,
    chrome: { ...OPENCODE_TICKET.chrome, locality: "frontier" } };
  assert.equal(isWellFormedWorkerTicket(t), false);
});

test("an opencode_local ticket may not launch any binary but opencode", () => {
  // The whole point of the allowlist (validator FINDING 1): a ticket declaring a lease-free local
  // adapter while pointing `executable` at a frontier CLI is an uncounted frontier terminal.
  for (const exe of ["C:/bin/claude.EXE", "C:/bin/ollama.EXE", "C:/bin/codex.exe"]) {
    const t = { ...OPENCODE_TICKET,
      launch: { ...OPENCODE_TICKET.launch, executable: exe, argv: [exe, "C:/repo"] } };
    assert.equal(isWellFormedWorkerTicket(t), false, `${exe} must not launch as opencode_local`);
  }
});

test("an opencode_local ticket whose argv[0] disagrees with its executable is refused", () => {
  // two separate facts, two separate checks — deleting either left the suite green (MAJOR-1).
  const t = { ...OPENCODE_TICKET,
    launch: { ...OPENCODE_TICKET.launch,
      argv: ["C:/bin/ollama.EXE", "C:/repo/worktrees/coding-1"] } };
  assert.equal(isWellFormedWorkerTicket(t), false);
});

test("an ollama_local ticket may not launch opencode either — the allowlist cuts both ways", () => {
  const t = { ...LOCAL_TICKET,
    launch: { ...LOCAL_TICKET.launch, executable: "C:/npm/opencode.CMD",
      argv: ["C:/npm/opencode.CMD", "C:/repo"] } };
  assert.equal(isWellFormedWorkerTicket(t), false);
});

// ---- (3) the two frontierClaim guards that had no coverage of their own ----
// Both are behaviour-bearing and both left the suite GREEN when deleted, on a function whose
// failure mode is an I-X3 terminal counted against the WRONG subscription, or a local ticket
// carrying one at all (independent gate-validator MINOR-1, 2026-07-26). Same class as the MAJOR-1
// the executable/argv[0] pair was split for, on the lines that split did not reach.

test("a frontier ticket counted against the OTHER provider's subscription is refused", () => {
  // the ref must be this adapter's own: a claude terminal billed to the codex allowance is an
  // UNCOUNTED claude terminal, which is exactly what I-X3 exists to prevent.
  const t = {
    ...FRONTIER_TICKET,
    identity: { ...FRONTIER_TICKET.identity, subscription_ref: "sub-openai_codex_cli" },
    lease: { ...FRONTIER_TICKET.lease, subscription_ref: "sub-openai_codex_cli" },
  };
  assert.equal(isWellFormedWorkerTicket(t), false);
  // …and the unmodified ticket still passes, so the check is discriminating, not blanket
  assert.equal(isWellFormedWorkerTicket(FRONTIER_TICKET), true);
});

test("a LOCAL ticket carrying a subscription_ref is refused", () => {
  // a local node holds no subscription terminal (invariant 19); one that declares a ref is either
  // producer drift or a frontier launch wearing local clothes.
  const t = { ...LOCAL_TICKET,
    identity: { ...LOCAL_TICKET.identity, subscription_ref: "sub-claude_code" } };
  assert.equal(isWellFormedWorkerTicket(t), false);
  assert.equal(isWellFormedWorkerTicket(LOCAL_TICKET), true);
});

test("a frontier ticket whose subscription_ref is whitespace is refused", () => {
  const t = { ...FRONTIER_TICKET,
    identity: { ...FRONTIER_TICKET.identity, subscription_ref: "   " } };
  assert.equal(isWellFormedWorkerTicket(t), false);
});

test("an EMPTY refused_by does not count as naming a gate", () => {
  // `typeof "" === "string"` let a producer that dropped the id stay well-formed while every
  // receipt leg comparing against a gate id silently stopped firing (validator MINOR-3).
  const base = { schema: WORKER_TICKET_SCHEMA, authorized: false, refused: true, reason: "no" };
  assert.equal(isWellFormedWorkerTicket({ ...base, refused_by: "vram_admission" }), true);
  for (const bad of ["", "   ", null, undefined, 7]) {
    assert.equal(isWellFormedWorkerTicket({ ...base, refused_by: bad }), false,
      `refused_by=${JSON.stringify(bad)} must not pass as a named gate`);
  }
});

test("redirection metacharacters are refused like the rest of the class", () => {
  // the stated goal is "closes the class rather than one instance"; `>` and `<` were missing.
  for (const arg of ["> out.txt", "<in.txt", "--model=a>b"]) {
    const t = { ...FRONTIER_TICKET,
      launch: { ...FRONTIER_TICKET.launch, argv: ["claude", "--model", arg] } };
    assert.equal(isWellFormedWorkerTicket(t), false, `argv carrying ${arg} must be refused`);
  }
  const exe = { ...FRONTIER_TICKET,
    launch: { ...FRONTIER_TICKET.launch, executable: "C:/bin/claude.EXE > x" } };
  assert.equal(isWellFormedWorkerTicket(exe), false);
});

// ---- the QUIT-path release (Phase 17B `.spawn`) -------------------------------------------------
// `before-quit` cannot await, so the blocking release is what actually hands a worker's durable
// terminal back when the operator closes the app. It shipped untested while its conductor twin was
// covered (validator MINOR-1) — an untested function on the only path that runs at quit.

test("releaseWorkerTerminalSync parses a real release, and fails closed on anything else", () => {
  const ok = releaseWorkerTerminalSync("pane-2#7.1", {
    spawnSync: (cmd, args, opts) => {
      assert.equal(cmd, "py");
      assert.deepEqual(args.slice(-3), ["tools/live/emit_worker_launch.py", "--release-session", "pane-2#7.1"]);
      assert.equal(opts.cwd, REPO_ROOT);
      return { status: 0, stdout: JSON.stringify({ schema: "terminal_lease_release@1.0", released: true, released_count: 1 }) };
    },
    cwd: REPO_ROOT,
  });
  assert.deepEqual(ok, { ok: true, released: true, count: 1 });

  const noSession = releaseWorkerTerminalSync("", {});
  assert.equal(noSession.released, false);

  for (const [label, res] of [
    ["non-zero exit", { status: 3, stdout: "" }],
    ["non-JSON", { status: 0, stdout: "not json" }],
    ["a drifted payload", { status: 0, stdout: JSON.stringify({ schema: "other@1.0", released: true }) }],
    ["a spawn error", { error: new Error("ENOENT") }],
  ]) {
    const r = releaseWorkerTerminalSync("pane-2#7.1", { spawnSync: () => res });
    assert.equal(r.released, false, `${label} must never read as a released terminal`);
    assert.ok(r.error, `${label} must say what went wrong`);
  }
});

// ---- the OP-12 providers through the SHELL-side ticket validator (18B `.picker`, review round 1) --
// Both reviewers found this arm missing entirely: `launch-source.js` learned four OP-12 facts —
// `ADAPTER_EXECUTABLE`, `FRONTIER_ADAPTERS`, `ADAPTER_SUBSCRIPTION_REF` and the `grok|agy` tokens in
// `FRONTIER_TOKENS` — while this file contained no occurrence of `grok`, `agy` or `antigravity`
// (validator BLOCKING-2). Reverting any one of the four left all 640 tests green, and one of them —
// the token rule — is the guard that stops a `grok` invocation from riding in as an "uncounted local
// terminal" with no I-X3 lease (invariant 21 / operator directive §12). Each test below goes RED on
// the single-line revert of the property it names.

const OP12_TICKETS = {
  grok_build: {
    executable: "C:/Users/x/AppData/Roaming/npm/grok.CMD", argv0: "grok",
    ref: "grok_build_subscription", label: "grok-4.5", model: "grok-4.5",
  },
  google_antigravity: {
    executable: "C:/Users/x/AppData/Local/agy/bin/agy.EXE", argv0: "agy",
    ref: "google_antigravity_subscription", label: "gemini-3.6-flash-high",
    model: "gemini-3.6-flash-high",
  },
};

const op12Ticket = (adapter, over = {}) => {
  const spec = OP12_TICKETS[adapter];
  return {
    ...FRONTIER_TICKET,
    launch: { ...FRONTIER_TICKET.launch, argv: [spec.argv0, "--model", spec.model],
      executable: spec.executable, ...(over.launch || {}) },
    chrome: { ...FRONTIER_TICKET.chrome, provider: adapter, adapter,
      model_label: spec.label, ...(over.chrome || {}) },
    identity: { ...FRONTIER_TICKET.identity, subscription_ref: spec.ref, ...(over.identity || {}) },
    lease: { ...FRONTIER_TICKET.lease, subscription_ref: spec.ref, provider: adapter,
      allowance: 1, ...(over.lease || {}) },
    model_probe: { label: spec.label, model: spec.model, model_available: true,
      source: "cli-enumeration" },
  };
};

test("a well-formed grok / antigravity frontier ticket is accepted by the shell validator", () => {
  for (const adapter of Object.keys(OP12_TICKETS)) {
    assert.equal(isWellFormedWorkerTicket(op12Ticket(adapter)), true,
      `${adapter}: a correct OP-12 ticket must not be refused by the shell`);
  }
});

test("an OP-12 ticket counted against the DERIVED ref the operator did not name is refused", () => {
  // OP-12 §12 named these two resources literally; `sub-${adapter}` is the spelling the pre-18B code
  // derived, and a terminal counted in a bucket nothing else reads is the U76 two-bucket defect.
  for (const adapter of Object.keys(OP12_TICKETS)) {
    const t = op12Ticket(adapter, { identity: { subscription_ref: `sub-${adapter}` } });
    assert.equal(isWellFormedWorkerTicket(t), false,
      `${adapter}: the wrong subscription ref must be refused`);
  }
});

test("an OP-12 ticket counted against the OTHER OP-12 provider's subscription is refused", () => {
  const swapped = op12Ticket("grok_build",
    { identity: { subscription_ref: OP12_TICKETS.google_antigravity.ref } });
  assert.equal(isWellFormedWorkerTicket(swapped), false);
  const other = op12Ticket("google_antigravity",
    { identity: { subscription_ref: OP12_TICKETS.grok_build.ref } });
  assert.equal(isWellFormedWorkerTicket(other), false);
});

test("an OP-12 ticket whose binary is the OTHER provider's CLI is refused (identity vs executable)", () => {
  // §14: a launch is frontier only when adapter, locality, subscription ref and the ACTUAL binary
  // agree. `agy` declared while `grok` is what runs is exactly the disagreement `frontierClaim` exists
  // for — and it is how one provider's terminal gets counted on the other's allowance-1 subscription.
  const agyRunningGrok = op12Ticket("google_antigravity", {
    launch: { executable: "C:/bin/grok.CMD", argv: ["grok", "--model", "grok-4.5"] } });
  assert.equal(isWellFormedWorkerTicket(agyRunningGrok), false);
  const grokRunningAgy = op12Ticket("grok_build", {
    launch: { executable: "C:/bin/agy.EXE", argv: ["agy", "--model", "gemini-3.6-flash-high"] } });
  assert.equal(isWellFormedWorkerTicket(grokRunningAgy), false);
  // …and the halves are separately load-bearing: the executable alone, then argv[0] alone
  assert.equal(isWellFormedWorkerTicket(op12Ticket("grok_build",
    { launch: { executable: "C:/bin/agy.EXE" } })), false);
  assert.equal(isWellFormedWorkerTicket(op12Ticket("grok_build",
    { launch: { argv: ["agy", "--model", "grok-4.5"] } })), false);
});

test("an OP-12 ticket relabelled LOCAL is refused — an unleased grok terminal is the whole point", () => {
  for (const adapter of Object.keys(OP12_TICKETS)) {
    const t = op12Ticket(adapter, {
      chrome: { locality: "local" }, identity: { subscription_ref: null },
    });
    const relabelled = { ...t, lease: null, subscription_governed: false, release_with: null };
    assert.equal(isWellFormedWorkerTicket(relabelled), false,
      `${adapter}: a frontier CLI must never pass as a lease-free local launch`);
  }
});

test("a LOCAL ticket whose argv merely NAMES grok or agy is refused, however it is wrapped", () => {
  // The FRONTIER_TOKENS guard: without `grok|agy` in it, every one of these reads as an ordinary
  // local ollama launch — no subscription ref, no lease, no I-X3 count, and a frontier CLI running.
  const wrapped = [
    ["grok", ["C:/bin/ollama.EXE", "run", "grok"]],
    ["a windows path", ["C:/bin/ollama.EXE", "run", "C:/Users/x/AppData/Roaming/npm/grok.CMD"]],
    ["a leading space", ["C:/bin/ollama.EXE", "run", " grok --model grok-4.5"]],
    ["agy", ["C:/bin/ollama.EXE", "run", "agy"]],
    ["an agy path", ["C:/bin/ollama.EXE", "run", "C:/Users/x/AppData/Local/agy/bin/agy.EXE"]],
    ["a quoted agy", ["C:/bin/ollama.EXE", "run", '"agy"']],
  ];
  for (const [label, argv] of wrapped) {
    const t = { ...LOCAL_TICKET, launch: { ...LOCAL_TICKET.launch, argv } };
    assert.equal(isWellFormedWorkerTicket(t), false,
      `a local ticket naming a frontier CLI (${label}) must be refused`);
  }
  // …and the rule still admits an honest local launch that merely CONTAINS those letters inside a
  // longer word: `agy` is short, and refusing every model tag that ends in it would be a defect.
  const honest = { ...LOCAL_TICKET,
    launch: { ...LOCAL_TICKET.launch, argv: ["C:/bin/ollama.EXE", "run", "magyar-7b"] } };
  assert.equal(isWellFormedWorkerTicket(honest), true,
    "a local model tag containing the letters agy is not a frontier invocation");
});

// ---- 18E: the post-spawn node attestation --------------------------------------------------------

test("attestWorkerPaneSpawned sends the node key and pid and reports the emitter's answer", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({
    schema: "worker_pane_spawn_attestation@1.0", node_key: "worker-pane-2", pid: 31337,
    attested: true, incarnation: 1, state: "READY", error: null }) });
  const res = await attestWorkerPaneSpawned("worker-pane-2", SESSION, 31337, { cwd: REPO_ROOT, spawn });
  assert.equal(res.ok, true);
  assert.equal(res.attested, true);
  assert.equal(res.state, "READY");
  const args = spawn.calls[0].args;
  assert.ok(args.includes("--record-pane-spawned") && args.includes("worker-pane-2"));
  assert.ok(args.includes("--session-id") && args.includes(SESSION));
  assert.ok(args.includes("--pid") && args.includes("31337"));
});

test("attestWorkerPaneSpawned NEVER throws and never reports a refusal as attested", async () => {
  const cases = [
    ["a non-zero exit", fakeSpawn({ stdout: "", stderr: "boom", code: 1 })],
    ["non-JSON", fakeSpawn({ stdout: "not json" })],
    ["a drifted schema", fakeSpawn({ stdout: JSON.stringify({ schema: "other@1.0", attested: true }) })],
    ["a spawn fault", fakeSpawn({ throwOnSpawn: true })],
  ];
  for (const [label, spawn] of cases) {
    const res = await attestWorkerPaneSpawned("worker-pane-2", SESSION, 31337, { cwd: REPO_ROOT, spawn });
    assert.equal(res.attested, false, `${label}: must not read as attested`);
    assert.ok(res.error, `${label}: must say what went wrong`);
  }
  // ...and a well-formed REFUSAL from the emitter is reported as one, not as an error-free pass.
  const refused = fakeSpawn({ stdout: JSON.stringify({
    schema: "worker_pane_spawn_attestation@1.0", node_key: "worker-pane-2", pid: 1,
    attested: false, error: "no registered node worker-pane-2 to attest" }) });
  const res = await attestWorkerPaneSpawned("worker-pane-2", SESSION, 1, { cwd: REPO_ROOT, spawn: refused });
  assert.equal(res.ok, true);
  assert.equal(res.attested, false);
  assert.match(res.error, /never written|no registered node/);
});

test("an attestation with no pid, no session or no node key never reaches the emitter", async () => {
  for (const [key, sid, pid] of [["", SESSION, 1], ["worker-pane-2", "", 1],
    ["worker-pane-2", SESSION, 0], ["worker-pane-2", SESSION, -3],
    ["worker-pane-2", SESSION, null]]) {
    const spawn = fakeSpawn({ stdout: "{}" });
    const res = await attestWorkerPaneSpawned(key, sid, pid, { cwd: REPO_ROOT, spawn });
    assert.equal(res.attested, false);
    assert.equal(spawn.calls.length, 0,
      "the attestation's whole content is a live supervised pid - asking without one is asking "
      + "the log to record a process nobody saw");
  }
});
