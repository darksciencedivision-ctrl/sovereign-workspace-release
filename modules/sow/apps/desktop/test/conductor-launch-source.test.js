"use strict";
/**
 * CONDUCTOR launch-ticket SOURCE tests (Phase 17A `.lease`) — the glue that turns the Python governed
 * launch emitter (`tools/live/emit_conductor_launch.py`) into something the shell can EXECUTE in pane
 * 1's ConPTY, with a durable I-X3 lease the shell holds and hands back.
 *
 * Two layers, mirroring conductor-spawn-source.test.js:
 *   (1) unit — a FAKE spawn proves the parse + timeout + fail-closed fold deterministically: an
 *       authorized ticket, a governed refusal, a HEADLESS-argv drift (refused — the conductor pane is
 *       never a one-shot worker call), a lease-less "authorized" ticket (refused — an uncounted live
 *       terminal defeats I-X3), a missing holderPid, non-zero exit, non-JSON, timeout, spawn error;
 *       plus the pure env-scrub fold (names dropped, nothing else touched);
 *   (2) live integration — the REAL `py -3.12` emitter is invoked with THIS test process's pid as the
 *       holder, the ticket validated, and the lease RELEASED again in the same test (D-LOOP-1: no
 *       durable terminal outlives this run). On a host that lacks authorization or the `claude` CLI
 *       the ticket is an honest refusal — also a pass, never a fabricated launch. Skips without py.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { EventEmitter } = require("node:events");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");
const crypto = require("node:crypto");
const {
  ConductorLaunchSourceError, LAUNCH_TICKET_SCHEMA, LEASE_STATUS_SCHEMA,
  fetchConductorLaunchTicket, sourceConductorLaunchTicket, releaseConductorLease,
  releaseConductorLeaseSession, releaseConductorLeaseSessionSync,
  fetchLeaseStatus, unavailableTicket, isWellFormedTicket, scrubbedLaunchEnv,
} = require("../conductor/launch-source");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const HAVE_PY = spawnSync("py", ["-3.12", "--version"], { encoding: "utf8" }).status === 0;
const BOUNDARY_HOOK = path.join(REPO_ROOT, "tools", "live", "voice_turn_boundary.js");
// The rendering the HOST's hook dispatcher can actually parse (U162): PowerShell reads a leading
// quoted token as an expression, so a Windows hook command needs the call operator.
const BOUNDARY_SHELL = process.platform === "win32" ? "powershell" : "sh";
const q = (s) => (/\s/.test(s) ? `"${s}"` : s);
const BARE_COMMAND = `${q(process.execPath)} ${q(BOUNDARY_HOOK)}`;
const BOUNDARY_COMMAND = BOUNDARY_SHELL === "powershell" ? `& ${BARE_COMMAND}` : BARE_COMMAND;
const BOUNDARY_SETTINGS = JSON.stringify({
  hooks: {
    UserPromptSubmit: [{ hooks: [{ type: "command", command: BOUNDARY_COMMAND }] }],
    PreToolUse: [{ matcher: ".*", hooks: [{ type: "command", command: BOUNDARY_COMMAND }] }],
    PermissionRequest: [{ matcher: ".*", hooks: [{ type: "command", command: BOUNDARY_COMMAND }] }],
    ConfigChange: [{ hooks: [{ type: "command", command: BOUNDARY_COMMAND }] }],
    Stop: [{ hooks: [{ type: "command", command: BOUNDARY_COMMAND }] }],
    StopFailure: [{ hooks: [{ type: "command", command: BOUNDARY_COMMAND }] }],
    SessionEnd: [{ hooks: [{ type: "command", command: BOUNDARY_COMMAND }] }],
  },
});
const hash = (data) => crypto.createHash("sha256").update(data).digest("hex");

const GOOD_TICKET = {
  schema: LAUNCH_TICKET_SCHEMA,
  authorized: true,
  refused: false,
  reason: null,
  node_state: "launch_authorized",
  launch: {
    argv: ["claude", "--model", "fable-5", "--settings", BOUNDARY_SETTINGS],
    interactive: true,
    one_shot: false,
    env_credential_scrubbed: true,
    env_scrub_names: ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"],
    cwd: "D:/repo",
    executable: "C:/bin/claude.EXE",
  },
  chrome: { label: "CONDUCTOR", role: "conductor", governed: true, interactive: true, pinned: true },
  identity: {
    node_id: "conductor-pane-1", permission_profile_id: "pp-conductor-pane",
    subscription_ref: "sub-claude_code", session_id: "pane-1#1", workspace: "D:/repo",
    role: "conductor", mode: "attended",
  },
  authority_boundary: {
    schema: "voice_turn_boundary@1.0", supervisor_owned: true,
    non_executing_voice_turns: true, enforced_by_supervisor_process: false,
    permission_profile_id: "pp-conductor-pane",
    prompt_marker_format: "[[SOVEREIGN_VOICE_CHAT_V2:{turn_id_hex32}]] ",
    hook_relative_path: "tools/live/voice_turn_boundary.js",
    hook_sha256: hash(fs.readFileSync(BOUNDARY_HOOK)),
    hook_runtime: process.execPath, hook_argv: [process.execPath, BOUNDARY_HOOK],
    hook_command: BOUNDARY_COMMAND,
    hook_command_shell: BOUNDARY_SHELL,
    hook_command_verified: true,
    hook_command_probe: { shell: BOUNDARY_SHELL, exit_code: 0, decision: "deny" },
    settings_sha256: hash(Buffer.from(BOUNDARY_SETTINGS, "utf8")),
  },
  containment: { authorized: true, supervisor_bound: false, os_job_object: false, owed_to: "U25" },
  selection_record: { selection: { model: "fable-5" }, executing: { model: null, verified: false } },
  lease: {
    lease_id: "lease-abc123", subscription_ref: "sub-claude_code", provider: "claude_code",
    node_id: "conductor-pane-1", session_id: "pane-1#1", holder_pid: 4242,
    acquired_at: "2026-07-25T00:00:00+00:00",
    purpose: "conductor-pane-1", durable: true, in_use: 1, allowance: 2, seeded_from_ledger: [],
  },
  release_with: ["--release-lease", "lease-abc123"],
  governor_released: true,
  gates: {
    live_operation_authorized: true, provider_live: true, operator_terms_confirmed: true,
    cli_present: true, ix3_counted: true,
  },
};

const REFUSAL = {
  schema: LAUNCH_TICKET_SCHEMA,
  authorized: false,
  refused: true,
  reason: "SubscriptionLimitExceeded: subscription 'sub-claude_code' at allowance 2",
  node_state: "launch_refused",
  launch: null, chrome: null, lease: null, release_with: null, governor_released: true,
};

function fakeSpawn({ stdout = "", stderr = "", code = 0, neverExit = false, throwOnSpawn = false, emitError = null } = {}) {
  const calls = [];
  const spawn = (cmd, args, opts) => {
    calls.push({ cmd, args, opts });
    if (throwOnSpawn) throw new Error("ENOENT");
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
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

// ---- (1) unit: fake spawn ---------------------------------------------------
test("fetchConductorLaunchTicket parses an authorized ticket and passes the holder pid", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_TICKET) });
  const t = await fetchConductorLaunchTicket({ spawn, cwd: REPO_ROOT, holderPid: 4242, sessionId: "pane-1#1" });
  assert.equal(t.authorized, true);
  assert.equal(t.lease.lease_id, "lease-abc123");
  assert.deepEqual(spawn.calls[0].args.slice(-6),
    ["tools/live/emit_conductor_launch.py", "--emit-conductor-launch", "--holder-pid", "4242",
      "--session-id", "pane-1#1"]);
  assert.equal(spawn.calls[0].opts.cwd, REPO_ROOT);
});

test("fetchConductorLaunchTicket refuses without a holder pid (a lease needs a real owner)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_TICKET) });
  await assert.rejects(() => fetchConductorLaunchTicket({ spawn, cwd: REPO_ROOT, sessionId: "pane-1#1" }),
    (e) => e instanceof ConductorLaunchSourceError && /holderPid/.test(e.message));
  assert.equal(spawn.calls.length, 0, "no emitter run without an owner pid");
});

test("fetchConductorLaunchTicket accepts a governed refusal (authorized:false + reason)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(REFUSAL) });
  const t = await fetchConductorLaunchTicket({ spawn, cwd: REPO_ROOT, holderPid: 1, sessionId: "pane-1#1" });
  assert.equal(t.authorized, false);
  assert.match(t.reason, /allowance 2/);
});

test("a HEADLESS argv is refused — the conductor pane is never a one-shot worker call", async () => {
  const drift = { ...GOOD_TICKET, launch: { ...GOOD_TICKET.launch, argv: ["claude", "-p", "hi"] } };
  const spawn = fakeSpawn({ stdout: JSON.stringify(drift) });
  await assert.rejects(() => fetchConductorLaunchTicket({ spawn, cwd: REPO_ROOT, holderPid: 1, sessionId: "pane-1#1" }),
    (e) => /malformed/.test(e.message));
});

test("an authorized ticket with NO held lease is refused (an uncounted terminal defeats I-X3)", async () => {
  const noLease = { ...GOOD_TICKET, lease: null };
  assert.equal(isWellFormedTicket(noLease), false);
  const zero = { ...GOOD_TICKET, lease: { ...GOOD_TICKET.lease, in_use: 0 } };
  assert.equal(isWellFormedTicket(zero), false);
  const notDurable = { ...GOOD_TICKET, lease: { ...GOOD_TICKET.lease, durable: false } };
  assert.equal(isWellFormedTicket(notDurable), false);
});

test("fetchConductorLaunchTicket rejects a non-zero exit, surfacing stderr", async () => {
  const spawn = fakeSpawn({ stderr: "--holder-pid required", code: 2 });
  await assert.rejects(() => fetchConductorLaunchTicket({ spawn, cwd: REPO_ROOT, holderPid: 5, sessionId: "pane-1#1" }),
    (e) => /exited 2/.test(e.message) && /holder-pid/.test(e.message));
});

test("fetchConductorLaunchTicket rejects non-JSON (never fabricates an authorization)", async () => {
  const spawn = fakeSpawn({ stdout: "totally not json" });
  await assert.rejects(() => fetchConductorLaunchTicket({ spawn, cwd: REPO_ROOT, holderPid: 5, sessionId: "pane-1#1" }),
    (e) => /non-JSON/.test(e.message));
});

test("fetchConductorLaunchTicket times out and kills the child", async () => {
  const spawn = fakeSpawn({ neverExit: true });
  await assert.rejects(() => fetchConductorLaunchTicket({ spawn, cwd: REPO_ROOT, holderPid: 5, sessionId: "pane-1#1", timeoutMs: 30 }),
    (e) => /timed out/.test(e.message));
});

test("sourceConductorLaunchTicket never throws — it folds to the unavailable ticket", async () => {
  const spawn = fakeSpawn({ throwOnSpawn: true });
  const res = await sourceConductorLaunchTicket({ spawn, cwd: REPO_ROOT, holderPid: 5, sessionId: "pane-1#1" });
  assert.equal(res.ok, false);
  assert.equal(res.ticket.authorized, false);
  assert.equal(res.ticket.node_state, "launch_unavailable");
  assert.equal(res.ticket.launch, null);
  assert.equal(res.ticket.lease, null);
  assert.match(res.error, /ENOENT/);
});

test("the unavailable ticket is itself never mistaken for an authorization", () => {
  const u = unavailableTicket();
  assert.equal(u.authorized, false);
  assert.equal(isWellFormedTicket(u), false); // refused:false ⇒ not even a well-formed refusal
});

test("releaseConductorLease never throws and reports the release", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ schema: "terminal_lease_release@1.0", lease_id: "l1", released: true, subscriptions: {}, error: null }) });
  const r = await releaseConductorLease("l1", { spawn, cwd: REPO_ROOT });
  assert.equal(r.ok, true);
  assert.equal(r.released, true);
  assert.deepEqual(spawn.calls[0].args.slice(-2), ["--release-lease", "l1"]);

  const bad = fakeSpawn({ code: 2, stderr: "nope" });
  const r2 = await releaseConductorLease("l1", { spawn: bad, cwd: REPO_ROOT });
  assert.equal(r2.ok, false);
  assert.equal(r2.released, false);
  assert.match(r2.error, /exited 2/);
});

// ---- (1b) `.pty`: the session key, the bound workspace, the reclaim path ----
test("a ticket without a session key is refused (a terminal is counted per session, U75)", () => {
  const noSession = { ...GOOD_TICKET, identity: { ...GOOD_TICKET.identity, session_id: "" } };
  assert.equal(isWellFormedTicket(noSession), false);
  const mismatched = { ...GOOD_TICKET, lease: { ...GOOD_TICKET.lease, session_id: "other" } };
  assert.equal(isWellFormedTicket(mismatched), false, "the lease must be the one for THIS session");
});

test("a ticket without the governed workspace cwd is refused (U78(a) binding)", () => {
  const noCwd = { ...GOOD_TICKET, launch: { ...GOOD_TICKET.launch, cwd: "" } };
  assert.equal(isWellFormedTicket(noCwd), false);
});

test("a ticket without the RESOLVED executable is refused (the shell never resolves a name)", () => {
  const noExe = { ...GOOD_TICKET, launch: { ...GOOD_TICKET.launch, executable: "" } };
  assert.equal(isWellFormedTicket(noExe), false);
});

test("fetchConductorLaunchTicket requires a session id and refuses a ticket for another session", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_TICKET) });
  await assert.rejects(() => fetchConductorLaunchTicket({ spawn, cwd: REPO_ROOT, holderPid: 4242 }),
    (e) => e instanceof ConductorLaunchSourceError && /sessionId/.test(e.message));
  assert.equal(spawn.calls.length, 0, "no emitter run without a session key");

  const other = fakeSpawn({ stdout: JSON.stringify(GOOD_TICKET) });  // ticket says pane-1#1
  await assert.rejects(
    () => fetchConductorLaunchTicket({ spawn: other, cwd: REPO_ROOT, holderPid: 4242, sessionId: "pane-1#9" }),
    (e) => /authorizes session pane-1#1, not pane-1#9/.test(e.message));
});

test("releaseConductorLeaseSession reclaims by the key the shell chose (U77)", async () => {
  const payload = { schema: "terminal_lease_release@1.0", lease_id: null, session_id: "pane-1#1",
    released: true, released_count: 1, subscriptions: {}, error: null };
  const spawn = fakeSpawn({ stdout: JSON.stringify(payload) });
  const r = await releaseConductorLeaseSession("pane-1#1", { spawn, cwd: REPO_ROOT });
  assert.equal(r.ok, true);
  assert.equal(r.released, true);
  assert.deepEqual(spawn.calls[0].args.slice(-2), ["--release-session", "pane-1#1"]);

  const none = await releaseConductorLeaseSession("", { spawn, cwd: REPO_ROOT });
  assert.equal(none.released, false);
  assert.equal(spawn.calls.length, 1, "an empty key never runs the emitter (never a wildcard)");
});

test("releaseConductorLeaseSessionSync is bounded and never throws (the quit path)", () => {
  const ok = releaseConductorLeaseSessionSync("pane-1#1", {
    cwd: REPO_ROOT,
    spawnSync: () => ({ status: 0, stdout: JSON.stringify({ schema: "terminal_lease_release@1.0", released: true, released_count: 1 }) }),
  });
  assert.equal(ok.ok, true);
  assert.equal(ok.released, true);

  const timedOut = releaseConductorLeaseSessionSync("pane-1#1", {
    cwd: REPO_ROOT, spawnSync: () => ({ error: new Error("ETIMEDOUT"), status: null }),
  });
  assert.equal(timedOut.ok, false);
  assert.match(timedOut.error, /ETIMEDOUT/);

  const garbage = releaseConductorLeaseSessionSync("pane-1#1", {
    cwd: REPO_ROOT, spawnSync: () => ({ status: 0, stdout: "not json" }),
  });
  assert.equal(garbage.ok, false);
  assert.equal(releaseConductorLeaseSessionSync("").ok, false);
});

test("scrubbedLaunchEnv drops exactly the named vars and nothing else (§2.2)", () => {
  const base = { PATH: "/bin", ANTHROPIC_API_KEY: "sk-should-never-be-here", ANTHROPIC_BASE_URL: "x", LANG: "en" };
  const env = scrubbedLaunchEnv(GOOD_TICKET, base);
  assert.deepEqual(Object.keys(env).sort(), ["LANG", "PATH"]);
  assert.equal(base.ANTHROPIC_API_KEY, "sk-should-never-be-here", "the base env is never mutated");
  assert.deepEqual(scrubbedLaunchEnv(unavailableTicket(), base), { ...base });
});

// ---- (2) live integration: the REAL emitter ---------------------------------
test("live: the real emitter issues a governed ticket (or an honest refusal) and the lease is released", { skip: !HAVE_PY ? "py -3.12 unavailable" : false }, async (tctx) => {
  // SCRATCH ledger: a lease is keyed to (subscription_ref, node_id) and this test uses the
  // production conductor identity, so against the real ledger it would adopt and then release a
  // lease the operator's own running conductor may hold — uncounting a live session.
  const scratch = path.join(REPO_ROOT, ".sovereign_store", "leases", `test-17a-${process.pid}.json`);
  const SESSION = `test-17a-session-${process.pid}`;
  const prior = process.env.SOW_TERMINAL_LEASE_LEDGER;
  process.env.SOW_TERMINAL_LEASE_LEDGER = scratch;
  tctx.after(() => {
    if (prior === undefined) delete process.env.SOW_TERMINAL_LEASE_LEDGER;
    else process.env.SOW_TERMINAL_LEASE_LEDGER = prior;
    try { require("node:fs").rmSync(scratch, { force: true }); } catch { /* nothing to remove */ }
  });
  const res = await sourceConductorLaunchTicket({ cwd: REPO_ROOT, holderPid: process.pid, sessionId: SESSION, timeoutMs: 60000 });
  assert.equal(res.ok, true, `emitter unavailable: ${res.error}`);
  const t = res.ticket;
  assert.equal(t.schema, LAUNCH_TICKET_SCHEMA);
  if (!t.authorized) {
    // an un-authorized host is a legitimate outcome — assert it is an HONEST refusal, not a stub
    assert.equal(t.refused, true);
    assert.ok(t.reason && t.reason.length > 0);
    assert.equal(t.launch, null);
    assert.equal(t.lease, null);
    return;
  }
  // LOCAL-01 F-3. A LOCAL conductor is an AUTHORIZED ticket that holds no durable terminal, so it
  // reaches neither branch below: the refusal branch above (it is not refused) nor the frontier
  // assertions (there is no lease to count or release). Its contract is the mirror image and is
  // asserted as such — the absence of a lease is the property, not a gap in the test.
  //
  // Before this run every authorized outcome on this host was frontier, and with
  // `live_operation.json` absent the emitter always refused, so this test only ever exercised the
  // refusal branch. It is now reachable in three states and says so.
  if (t.conductor_descriptor && t.conductor_descriptor.locality === "local") {
    assert.equal(t.lease, null, "a local conductor holds no durable I-X3 terminal (invariant 19)");
    assert.equal(t.release_with, null, "there is nothing to hand back");
    assert.equal(t.identity.subscription_ref, "", "a local pane claims no subscription");
    assert.equal(t.chrome.subscription, null);
    assert.equal(t.launch.one_shot, false);
    assert.equal(t.launch.interactive, true);
    assert.equal(t.gates.ix3_counted, false);
    assert.equal(t.gates.locality, "local");
    assert.equal(t.gates.live_operation_authorized, null,
      "the live gate is NOT APPLICABLE to a local model — not merely unsatisfied");
    assert.deepEqual(t.launch.argv.slice(1), ["run", t.conductor_descriptor.model_id],
      "an interactive `ollama run <tag>` and nothing else");
    assert.equal(t.authority_boundary.schema, "conductor_local_boundary@1.0");
    assert.equal(t.authority_boundary.tool_surface, "none");
    return;
  }
  try {
    assert.equal(t.conductor_descriptor.provider_id, "openai_codex_cli");
    assert.equal(t.conductor_descriptor.model_id, "gpt-5.6-sol");
    assert.match(t.launch.argv[0], /codex/i);
    assert.equal(t.launch.one_shot, false);
    assert.ok(!t.launch.argv.includes("-p"));
    assert.ok(Array.isArray(t.launch.env_scrub_names));
    assert.equal(t.lease.holder_pid, process.pid);
    assert.equal(t.lease.durable, true);
    assert.ok(t.lease.in_use >= 1);
    assert.equal(t.governor_released, true, "the emitter's in-process count must not leak");
    assert.ok(t.identity && t.identity.node_id && t.identity.permission_profile_id,
      "the shell must be told which governed identity to spawn under (inv 2/29)");
    assert.equal(t.identity.session_id, SESSION, "the ticket is for the session the shell asked for");
    assert.equal(t.lease.session_id, SESSION, "the terminal is counted under that session (U75)");
    assert.ok(t.launch.cwd && t.launch.cwd.length > 0, "the governed workspace cwd must be carried");
    assert.ok(t.launch.executable && t.launch.executable.length > 0,
      "the ticket must carry the RESOLVED binary the presence gate found (a ConPTY takes a file)");
    assert.equal(t.containment.supervisor_bound, false,
      "a ticket is an authorization, not containment — it must say so until .pty binds it");

    const st = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: 60000 });
    assert.equal(st.ok, true);
    assert.equal(st.status.schema, LEASE_STATUS_SCHEMA);
    assert.ok(st.status.subscriptions[t.lease.subscription_ref].in_use >= 1,
      "the durable lease is visible to a SEPARATE process — the whole point");
  } finally {
    // D-LOOP-1: never leave a durable terminal behind, even if an assertion above failed.
    const rel = await releaseConductorLeaseSession(SESSION, { cwd: REPO_ROOT, timeoutMs: 60000 });
    assert.equal(rel.ok, true, `release failed: ${rel.error}`);
    const again = await releaseConductorLease(t.lease.lease_id, { cwd: REPO_ROOT, timeoutMs: 60000 });
    assert.equal(again.ok, true);
    assert.equal(again.released, false, "the session reclaim already handed it back");
  }
});

test("a banned flag in its --flag=value form is refused (both producers, one rule)", () => {
  // `--output-format=json` is the SAME flag as `--output-format json`. The worker contract split on
  // `=` and this one still exact-matched, so the conductor path stayed defeated by the `=value`
  // form — a fix that belonged to both copies (spec-audit MINOR-11, 2026-07-26).
  for (const flag of ["--output-format=json", "--print=1"]) {
    const drift = { ...GOOD_TICKET,
      launch: { ...GOOD_TICKET.launch, argv: ["claude", "--model", "fable-5", flag] } };
    assert.equal(isWellFormedTicket(drift), false, `${flag} must be refused`);
  }
  // the space-separated form still refused, and a legitimate argv still accepted
  assert.equal(isWellFormedTicket(GOOD_TICKET), true);
});

test("a shell metacharacter in the CONDUCTOR argv or executable is refused", () => {
  // The rule existed only in the worker copy, so the ticket the operator actually types into
  // accepted `&&`, `|`, `;`, `<`, `>`, a backtick or `$(` anywhere (validator MINOR-4, round 2).
  // It is tested HERE because adding the guard without a test is the same defect one level up:
  // deleting either new line left the whole 230-test suite green (validator MAJOR-2, round 3).
  for (const arg of ["fable-5 && whoami", "a|b", "x;y", "`id`", "$(id)", "> out.txt", "<in.txt"]) {
    const drift = { ...GOOD_TICKET,
      launch: { ...GOOD_TICKET.launch, argv: ["claude", "--model", arg] } };
    assert.equal(isWellFormedTicket(drift), false, `argv carrying ${arg} must be refused`);
  }
  for (const exe of ["C:/bin/claude.exe && whoami", "C:/bin/claude.exe > x", "`claude`"]) {
    const drift = { ...GOOD_TICKET, launch: { ...GOOD_TICKET.launch, executable: exe } };
    assert.equal(isWellFormedTicket(drift), false, `executable ${exe} must be refused`);
  }
  // …and a legitimate ticket is untouched: the guard discriminates, it does not blanket-refuse
  assert.equal(isWellFormedTicket(GOOD_TICKET), true);
});

test("the metacharacter exemption covers ONLY the value of a real --settings flag", () => {
  // Since U162 the permission-profile JSON legitimately carries `&`, so it is exempt from the
  // denylist — positionally, and only when the flag it belongs to is actually there. The same bytes
  // sitting in any other slot are still an argument nobody pinned.
  const drift = structuredClone(GOOD_TICKET);
  drift.launch.argv = ["claude", "--model", "fable-5", BOUNDARY_SETTINGS];
  assert.equal(isWellFormedTicket(drift), false,
    "a profile-shaped blob with no --settings flag is not an exempt payload");
});

test("a coherent-looking boundary that points its hook command elsewhere is refused", () => {
  const drift = structuredClone(GOOD_TICKET);
  const other = path.join(REPO_ROOT, "tools", "live", "emit_conductor_launch.py");
  const command = `"${process.execPath}" "${other}"`;
  const settingsAt = drift.launch.argv.indexOf("--settings") + 1;
  const settings = JSON.parse(drift.launch.argv[settingsAt]);
  for (const rows of Object.values(settings.hooks)) rows[0].hooks[0].command = command;
  const raw = JSON.stringify(settings);
  drift.launch.argv[settingsAt] = raw;
  drift.authority_boundary.hook_command = command;
  drift.authority_boundary.settings_sha256 = hash(Buffer.from(raw, "utf8"));
  assert.equal(isWellFormedTicket(drift), false,
    "the shell ties the command to the hash-pinned hook path; producer metadata cannot redirect it");
});

test("a hook command this host's dispatcher cannot parse is refused (U162)", () => {
  // The exact string iteration 92 shipped. PowerShell reads its leading quoted token as an
  // expression and never runs the hook, so the CLI reports a NON-BLOCKING hook error and executes
  // the tool anyway: the boundary fails OPEN while every field in it still looks right.
  const drift = structuredClone(GOOD_TICKET);
  const settingsAt = drift.launch.argv.indexOf("--settings") + 1;
  const settings = JSON.parse(drift.launch.argv[settingsAt]);
  for (const rows of Object.values(settings.hooks)) rows[0].hooks[0].command = BARE_COMMAND;
  const raw = JSON.stringify(settings);
  drift.launch.argv[settingsAt] = raw;
  drift.authority_boundary.hook_command = BARE_COMMAND;
  drift.authority_boundary.settings_sha256 = hash(Buffer.from(raw, "utf8"));
  assert.equal(isWellFormedTicket(drift), process.platform !== "win32",
    "on Windows the shell must refuse a command PowerShell would not run");
});

test("a boundary that does not name the dispatcher it was rendered for is refused", () => {
  for (const patch of [{ hook_command_shell: "bash" }, { hook_command_shell: undefined },
    { hook_command_verified: false }, { hook_command_verified: undefined }]) {
    const drift = structuredClone(GOOD_TICKET);
    Object.assign(drift.authority_boundary, patch);
    assert.equal(isWellFormedTicket(drift), false, `refused: ${JSON.stringify(patch)}`);
  }
});

test("an authorized conductor ticket without the applied permission profile is refused", () => {
  const drift = structuredClone(GOOD_TICKET);
  drift.authority_boundary = null;
  assert.equal(isWellFormedTicket(drift), false);
});

test("the hook profile cannot claim supervisor-process enforcement", () => {
  const drift = structuredClone(GOOD_TICKET);
  drift.authority_boundary.enforced_by_supervisor_process = true;
  assert.equal(isWellFormedTicket(drift), false);
});

test("containment selects a verified boundary profile, not an adapter-name branch", () => {
  const ticket = structuredClone(GOOD_TICKET);
  ticket.conductor_descriptor = {
    role: "conductor", provider_id: "future_provider", adapter_id: "future_adapter",
    model_id: "future-model", permission_profile_id: ticket.identity.permission_profile_id,
    registered: true, conductor_capable: true, readiness_turns: 1,
  };
  ticket.launch.argv = ["future", "-m", "future-model", "--sandbox", "read-only",
    "--ask-for-approval", "untrusted"];
  ticket.authority_boundary = {
    schema: "conductor_permission_boundary@1.0", provider: "future_adapter",
    permission_profile_id: ticket.identity.permission_profile_id, supervisor_owned: true,
    sandbox: "read-only", approval_policy: "untrusted", automatic_approval: false,
    unrestricted_tools: false,
  };
  assert.equal(isWellFormedTicket(ticket), true,
    "a known profile is verified without an adapter allowlist");
  ticket.authority_boundary.schema = "unknown_boundary@1.0";
  assert.equal(isWellFormedTicket(ticket), false, "an unknown profile fails closed");
});
