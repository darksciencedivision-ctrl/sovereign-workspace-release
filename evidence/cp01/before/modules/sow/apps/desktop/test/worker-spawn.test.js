"use strict";
/**
 * GOVERNED WORKER-PANE LAUNCH tests (Phase 17B `.spawn`, closes U70's spawn half).
 *
 * `picker/worker-spawn.js` is the ONLY place in the shell that executes a worker launch ticket, and
 * every rule in it is a governance rule, so every rule gets a test that goes RED when the line is
 * deleted. What is pinned here, in the order the launcher applies it:
 *
 *   1. admission before anything is counted (invariant 2) — no ticket is even requested;
 *   2. a pane holding a LIVE session is refused; an ENDED record is forgotten first;
 *   3. the session key is chosen BEFORE the ask, and an UNDELIVERED ticket still releases the
 *      terminal counted under it (U100 — the defect this sub-step owns);
 *   4. a governed refusal spawns nothing and carries the gate id verbatim;
 *   5. the child env is the ticket's scrub applied to the env the ticket was CLASSIFIED against
 *      (U105), and a name surviving the scrub ABORTS the spawn (§2.2);
 *   6. pre-birth failure releases; post-birth failure retains through matching process exit;
 *   7. D-LOOP-1: kill intent retains; exact exit releases; `heldSessions()` reports unreconciled rows.
 *
 * Every dependency is a fake — no Electron, no Python, no host. The live end-to-end is the
 * in-Electron receipt (`selfcheck/worker-spawn-selfcheck.js`).
 */
const { test } = require("node:test");
const assert = require("node:assert");

const { createWorkerPaneLauncher } = require("../picker/worker-spawn");

const CHROME = {
  provider: "ollama", adapter: "ollama_local", locality: "local", model_label: "qwen3:8b",
  model_slug: "qwen3:8b", role: "reasoning", mode: "attended", node_state: "launch_authorized",
  governed: true,
};

/** An AUTHORIZED local ticket (no lease, a residency decision) — the cheap, credential-free path. */
function localTicket(overrides = {}) {
  return {
    schema: "worker_launch_ticket@1.0",
    authorized: true, refused: false, reason: null, refused_by: null,
    launch: {
      argv: ["ollama", "run", "qwen3:8b"], executable: "C:/bin/ollama.exe",
      cwd: "C:/workspace", interactive: true, one_shot: false,
      env_scrub_names: ["ANTHROPIC_API_KEY"], env_credential_scrubbed: true,
    },
    chrome: { ...CHROME },
    identity: {
      node_id: "worker-pane-2", permission_profile_id: "pp-worker-reasoning",
      session_id: "pane-2#1.1", pane_id: "pane-2", subscription_ref: null,
    },
    containment: { authorized: true, supervisor_bound: false },
    lease: null, subscription_governed: false,
    residency: { model: "qwen3:8b", scheduled: true, status: "resident" },
    ...overrides,
  };
}

/** An AUTHORIZED frontier ticket — a durable I-X3 terminal is held for this session. */
function frontierTicket() {
  return {
    ...localTicket(),
    launch: {
      argv: ["claude", "--model", "claude-fable-5"], executable: "C:/bin/claude.exe",
      cwd: "C:/workspace", interactive: true, one_shot: false,
      env_scrub_names: ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"], env_credential_scrubbed: true,
    },
    chrome: { ...CHROME, adapter: "claude_code", locality: "frontier", model_label: "Fable 5" },
    identity: {
      node_id: "worker-pane-2", permission_profile_id: "pp-worker-reasoning",
      session_id: "pane-2#1.1", pane_id: "pane-2", subscription_ref: "sub-claude_code",
    },
    lease: { lease_id: "lease-1", durable: true, in_use: 1, allowance: 2,
      subscription_ref: "sub-claude_code", session_id: "pane-2#1.1" },
    subscription_governed: true, residency: null,
  };
}

const SELECTION = { option: { provider: "ollama", label: "qwen3:8b", adapter: "ollama_local",
  locality: "local", available: true, roles: ["reasoning"] }, role: "reasoning", mode: "attended" };

/** A launcher with recording fakes. `opts` overrides any dependency. */
function harness(opts = {}) {
  const calls = { tickets: [], releases: [], spawns: [], changes: [], attestations: [] };
  const scheduled = [];
  let lastSpawnIdentity = null;
  const launcher = createWorkerPaneLauncher({
    repoRoot: "C:/repo",
    holderPid: 4242,
    baseEnv: opts.baseEnv || { PATH: "C:/bin", ANTHROPIC_API_KEY: "never-read" },
    isSupervised: opts.isSupervised || (() => true),
    hasLiveSession: opts.hasLiveSession || (() => false),
    forgetSession: opts.forgetSession || (() => {}),
    ...(opts.scrubEnv ? { scrubEnv: opts.scrubEnv } : {}),
    ...(opts.augmentSpawnEnv ? { augmentSpawnEnv: opts.augmentSpawnEnv } : {}),
    ...(opts.revokeNodeControl ? { revokeNodeControl: opts.revokeNodeControl } : {}),
    sourceTicket: opts.sourceTicket || (async (o) => {
      calls.tickets.push(o);
      return { ok: true, ticket: localTicket() };
    }),
    releaseTerminal: opts.releaseTerminal || (async (sid) => {
      calls.releases.push(sid);
      return { ok: true, released: true };
    }),
    // INJECTED, always: the default is the real emitter call, and a headless suite that let it
    // through would shell out to `py -3.12` — and write into this host's DURABLE node log — once
    // per launch test. The node-record rule itself is driven by the Python suite; what these tests
    // pin is that the shell asks, with the right facts, and never lets the answer break a launch.
    attestSpawn: opts.attestSpawn || (async (nodeKey, sessionId, pid) => {
      calls.attestations.push({ nodeKey, sessionId, pid });
      return { ok: true, attested: true, state: "READY" };
    }),
    spawnSession: (s) => {
      const identity = opts.spawnSession
        ? opts.spawnSession(s)
        : (calls.spawns.push(s), { pid: 31337, generation: 9 });
      lastSpawnIdentity = identity;
      return identity;
    },
    processIdentity: opts.processIdentity || (() => lastSpawnIdentity),
    scheduleRetry: opts.scheduleRetry || ((fn) => {
      scheduled.push(fn);
      return { unref() {} };
    }),
    onChange: (paneId, rec) => calls.changes.push({ paneId, state: rec.state }),
    log: () => {},
  });
  return { launcher, calls, scheduled };
}

// ---- 1. admission first (invariant 2) ----------------------------------------------------------

test("no ticket is even REQUESTED while supervision is not READY (invariant 2)", async () => {
  const { launcher, calls } = harness({ isSupervised: () => false });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.launched, false);
  assert.equal(res.record.state, "unavailable");
  assert.match(res.reason, /supervision is not READY/);
  assert.equal(calls.tickets.length, 0, "asking would COUNT a terminal for a session that cannot be born");
  assert.equal(calls.spawns.length, 0);
});

test("the Python-issued worker identity receives node-scoped MCP control env before spawn", async () => {
  let augmented = null;
  const { launcher, calls } = harness({
    augmentSpawnEnv: (env, ctx) => {
      augmented = ctx;
      return { ...env, SOVEREIGN_CONTROL_PORT: "3210", SOVEREIGN_CONTROL_TOKEN: "opaque" };
    },
  });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.launched, true);
  assert.equal(augmented.identity.node_id, "worker-pane-2");
  assert.equal(augmented.paneId, "pane-2");
  assert.equal(calls.spawns[0].spec.env.SOVEREIGN_CONTROL_TOKEN, "opaque");
});

test("a pre-birth failure revokes the node MCP capability before lease reconciliation", async () => {
  const revoked = [];
  const { launcher, calls } = harness({
    augmentSpawnEnv: (env) => ({ ...env, SOVEREIGN_CONTROL_TOKEN: "opaque" }),
    revokeNodeControl: (nodeId) => revoked.push(nodeId),
    spawnSession: () => { throw new Error("pty refused"); },
  });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.launched, false);
  assert.deepEqual(revoked, ["worker-pane-2"]);
  assert.equal(calls.releases.length, 1);
});

test("a selection with no picker option is refused before any gate is asked", async () => {
  const { launcher, calls } = harness();
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: { role: "reasoning" } });
  assert.equal(res.launched, false);
  assert.equal(calls.tickets.length, 0);
});

// ---- 2. the pane must be free ------------------------------------------------------------------

test("a pane already holding a LIVE session is refused — the running session is never killed", async () => {
  const { launcher, calls } = harness({ hasLiveSession: () => true });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.launched, false);
  assert.match(res.reason, /already holds a live session/);
  assert.equal(calls.tickets.length, 0);
});

test("a refusal into a pane holding a LIVE session leaves that session's release accounting intact", async () => {
  // The defect this pins (gate-validator BLOCKING-1): `refuse()` merged into the pane's record, so
  // the occupied-pane refusal overwrote the RUNNING record of the session it had just declined to
  // disturb. Every release gate keys on the state, so the durable terminal became unreleasable for
  // the life of the shell — on exit, on kill, AND on quit. The previous occupied-pane test could not
  // see it: it refused into a pane this launcher had never launched into, so there was no live
  // record to clobber.
  let live = false;
  const { launcher, calls } = harness({
    sourceTicket: async () => ({ ok: true, ticket: frontierTicket() }),
    hasLiveSession: () => live,
  });
  const first = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(first.launched, true);
  live = true;

  const second = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(second.launched, false);
  assert.match(second.reason, /already holds a live session/);
  assert.equal(second.heldSessionUntouched, true, "the caller must be told the pane still holds one");

  // the record still describes the RUNNING session, not the refusal
  const rec = launcher.record("pane-2");
  assert.equal(rec.state, "running");
  assert.equal(rec.sessionId, "pane-2#4242.1");
  assert.equal(rec.leaseId, "lease-1");
  // …so teardown/dead-holder reconciliation still knows this terminal remains held…
  assert.deepEqual(launcher.heldSessions(), ["pane-2#4242.1"]);
  // …and so does the exit hook.
  const r = await launcher.onWorkerSessionEnded({
    id: "pane-2", kind: "exit", processExited: true, generation: 9, pid: 31337, exitCode: 0,
  });
  assert.equal(r.released, true);
  assert.deepEqual(calls.releases, ["pane-2#4242.1"]);
});

test("a refusal into a pane whose session already ENDED does record the refusal", async () => {
  // The other half of the same rule: only a LIVE record is protected. A pane whose session ended
  // must still show why the next attempt was refused, or the operator gets a silent no-op.
  const { launcher } = harness();
  await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  await launcher.onWorkerSessionEnded({
    id: "pane-2", kind: "exit", processExited: true, generation: 9, pid: 31337, exitCode: 0,
  });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: { role: "reasoning" } });
  assert.equal(res.launched, false);
  assert.equal(res.heldSessionUntouched, false);
  assert.equal(launcher.record("pane-2").state, "refused");
});

test("an ENDED session record is forgotten first, so it cannot wedge the pane", async () => {
  let forgot = 0;
  const { launcher } = harness({ forgetSession: () => { forgot += 1; } });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(forgot, 1);
  assert.equal(res.launched, true);
});

test("a registry that REFUSES to forget (a live record) refuses the launch instead of orphaning it", async () => {
  const { launcher, calls } = harness({
    forgetSession: () => { throw new Error("session pane-2 is live"); },
  });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.launched, false);
  assert.match(res.reason, /still carries a live session record/);
  assert.equal(calls.tickets.length, 0);
});

// ---- 3. the session key, and U100 --------------------------------------------------------------

test("the session key is chosen BEFORE the ask and is what the ticket is requested for", async () => {
  const { launcher, calls } = harness();
  await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(calls.tickets.length, 1);
  assert.equal(calls.tickets[0].sessionId, "pane-2#4242.1");
  assert.equal(calls.tickets[0].paneId, "pane-2");
  assert.equal(calls.tickets[0].holderPid, 4242);
});

test("U100: an UNDELIVERED ticket still releases the terminal counted under our session key", async () => {
  const { launcher, calls } = harness({
    sourceTicket: async () => ({ ok: false, error: "WorkerLaunchSourceError: emitter timed out" }),
  });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.launched, false);
  assert.equal(res.record.state, "unavailable");
  assert.match(res.reason, /timed out/);
  // the reclaim key is OURS: the emitter may have taken the terminal before it failed
  assert.deepEqual(calls.releases, ["pane-2#4242.1"]);
  assert.equal(calls.spawns.length, 0);
});

// ---- 4. a governed refusal --------------------------------------------------------------------

test("a governed refusal spawns nothing and carries the gate id verbatim", async () => {
  const { launcher, calls } = harness({
    sourceTicket: async () => ({ ok: true, ticket: {
      schema: "worker_launch_ticket@1.0", authorized: false, refused: true,
      reason: "residency/VRAM planner refused 'qwen3:8b'", refused_by: "vram_admission",
      launch: null, lease: null,
    } }),
  });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.launched, false);
  assert.equal(res.refused, true);
  assert.equal(res.refusedBy, "vram_admission");
  assert.match(res.reason, /VRAM planner refused/);
  assert.equal(res.record.state, "refused");
  assert.equal(calls.spawns.length, 0);
  assert.deepEqual(calls.releases, ["pane-2#4242.1"]);
});

// ---- 5. the child environment (§2.2 / U105) ----------------------------------------------------

test("the shell's OWN env var names are sent for classification, and the env is the same one spawned from (U105)", async () => {
  const baseEnv = { PATH: "C:/bin", ANTHROPIC_API_KEY: "never-read", HOME: "C:/u" };
  const { launcher, calls } = harness({ baseEnv });
  await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(calls.tickets[0].shellEnv, baseEnv,
    "the env classified must BE the env spawned from — two environments, two lists (U105)");
  const spawned = calls.spawns[0].spec.env;
  assert.equal("ANTHROPIC_API_KEY" in spawned, false, "the named credential var reached the child (§2.2)");
  assert.equal(spawned.PATH, "C:/bin", "a non-credential var was dropped — the scrub is by NAME, not by class");
  assert.equal(baseEnv.ANTHROPIC_API_KEY, "never-read", "the shell's own env must not be mutated");
});

test("a named var SURVIVING the scrub aborts the spawn and hands the terminal back (§2.2)", async () => {
  // The DEFAULT scrub cannot leave one behind, so the guard is driven through the injected scrub —
  // the only reason it is injectable. A shell whose child env still holds a named credential var is
  // the §2.2 failure the list exists to prevent, so the spawn is aborted, not warned about.
  const { launcher, calls } = harness({
    scrubEnv: (_t, base) => ({ ...base }),        // a scrub that scrubs nothing
    baseEnv: { PATH: "C:/bin", ANTHROPIC_API_KEY: "never-read" },
  });
  const res = await launcher.launchWorkerPane({ paneId: "pane-3", selection: SELECTION });
  assert.equal(res.launched, false);
  assert.equal(res.record.state, "failed");
  assert.match(res.reason, /credential scrub left 1 named var/);
  assert.deepEqual(calls.releases, ["pane-3#4242.1"]);
  assert.equal(calls.spawns.length, 0, "no session is born with a credential var in its environment");
});

test("the leftover guard matches CASE-INSENSITIVELY — the exact divergence U105 exists for", async () => {
  // Both reviewers found this rule unpinned: the test above drives the guard with a name spelled
  // identically in the list and in the env, so it passed just as happily against the exact-spelling
  // guard the fix REPLACED (validator MINOR-1 / spec-audit MINOR-2). Windows env var names are
  // case-insensitive to the OS while a plain-object delete is case-sensitive, so the leak that
  // actually happens on this host is a list saying `ANTHROPIC_API_KEY` and a child still holding
  // `Anthropic_Api_Key`. An exact-spelling guard is blind to precisely the class it guards against.
  const { launcher, calls } = harness({
    scrubEnv: (_t, base) => {
      // a scrub that deletes by EXACT spelling only — i.e. the U105 defect itself, reproduced
      const out = { ...base };
      delete out.ANTHROPIC_API_KEY;
      return out;
    },
    baseEnv: { PATH: "C:/bin", Anthropic_Api_Key: "never-read" },
  });
  const res = await launcher.launchWorkerPane({ paneId: "pane-3", selection: SELECTION });
  assert.equal(res.launched, false, "a differently-cased credential var reached the child (§2.2)");
  assert.equal(res.record.state, "failed");
  assert.match(res.reason, /credential scrub left 1 named var/);
  assert.equal(calls.spawns.length, 0);
  assert.deepEqual(calls.releases, ["pane-3#4242.1"], "the terminal is handed back on the abort");
});

// ---- the authorized spawn itself ---------------------------------------------------------------

test("an AUTHORIZED ticket spawns exactly the gated binary, argv, cwd and PYTHON-minted node id", async () => {
  const { launcher, calls } = harness();
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.launched, true);
  const s = calls.spawns[0];
  assert.equal(s.paneId, "pane-2");
  assert.equal(s.nodeId, "worker-pane-2", "the shell must never mint its own node identity (inv 2/29)");
  assert.equal(s.spec.file, "C:/bin/ollama.exe", "the RESOLVED binary, not a PATH-searched name");
  assert.deepEqual(s.spec.args, ["run", "qwen3:8b"]);
  assert.equal(s.spec.cwd, "C:/workspace", "the governed workspace, not the shell's cwd");
  assert.equal(res.record.state, "running");
  assert.equal(res.record.subscriptionGoverned, false);
  assert.deepEqual(res.record.residency, { model: "qwen3:8b", scheduled: true, status: "resident" });
  assert.equal(res.record.envScrubNames.length, 1);
});

test("a FRONTIER launch records the durable lease it holds; a LOCAL one records none", async () => {
  const { launcher } = harness({ sourceTicket: async () => ({ ok: true, ticket: frontierTicket() }) });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.record.subscriptionGoverned, true);
  assert.equal(res.record.leaseId, "lease-1");
  assert.equal(res.record.subscriptionRef, "sub-claude_code");
  assert.equal(res.record.residency, null);
});

// ---- 6. a spawn that throws --------------------------------------------------------------------

test("a spawn that throws (supervision denied / ConPTY failure) hands the terminal straight back", async () => {
  const { launcher, calls } = harness({
    spawnSession: () => { const e = new Error("supervision denied"); e.name = "SupervisionDenied"; throw e; },
  });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.launched, false);
  assert.equal(res.record.state, "failed");
  assert.match(res.reason, /SupervisionDenied: supervision denied/);
  assert.deepEqual(calls.releases, ["pane-2#4242.1"],
    "a terminal granted for a session that does not exist is 1 of the operator's 2, held by nothing");
});

test("a failed pre-birth release stays held and retries instead of being forgotten", async () => {
  let attempts = 0;
  const { launcher, calls, scheduled } = harness({
    spawnSession: () => { throw new Error("ConPTY construction failed"); },
    releaseTerminal: async (sid) => {
      calls.releases.push(sid);
      attempts += 1;
      return attempts === 1
        ? { ok: false, released: false, error: "temporary emitter failure" }
        : { ok: true, released: true };
    },
  });

  const result = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(result.launched, false);
  assert.equal(result.record.state, "release_failed");
  assert.deepEqual(launcher.heldSessions(), ["pane-2#4242.1"]);
  assert.equal(scheduled.length, 1);

  await scheduled[0]();
  assert.equal(launcher.record("pane-2").state, "failed");
  assert.deepEqual(launcher.heldSessions(), []);
});

test("a spawn failure after PTY birth holds the terminal until that exact process exits", async () => {
  const pending = Object.assign(new Error("post-spawn pane wiring failed"), {
    sessionIdentity: { pid: 31337, generation: 9 },
    processExitPending: true,
  });
  const { launcher, calls } = harness({
    sourceTicket: async () => ({ ok: true, ticket: frontierTicket() }),
    spawnSession: () => { throw pending; },
  });
  const result = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(result.launched, false);
  assert.equal(result.record.state, "terminating");
  assert.equal(result.record.leaseId, "lease-1");
  assert.deepEqual(calls.releases, []);
  await launcher.onWorkerSessionEnded({
    id: "pane-2", kind: "exit", processExited: true, generation: 9, pid: 31337, exitCode: 1,
  });
  assert.deepEqual(calls.releases, ["pane-2#4242.1"]);
});

// ---- 7. D-LOOP-1 --------------------------------------------------------------------------------

test("the session ending releases the durable terminal and records the exit honestly (D-LOOP-1)", async () => {
  const { launcher, calls } = harness({ sourceTicket: async () => ({ ok: true, ticket: frontierTicket() }) });
  await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.deepEqual(launcher.heldSessions(), ["pane-2#4242.1"]);
  const r = await launcher.onWorkerSessionEnded({
    id: "pane-2", kind: "exit", processExited: true, generation: 9, pid: 31337, exitCode: 0,
  });
  assert.equal(r.released, true);
  assert.deepEqual(calls.releases, ["pane-2#4242.1"]);
  const rec = launcher.record("pane-2");
  assert.equal(rec.state, "exited");
  assert.equal(rec.exitCode, 0);
  assert.equal(rec.leaseId, null);
  assert.deepEqual(launcher.heldSessions(), [], "an ended session must not still be reported as held");
});

test("a failed exit-time release remains held and retries without another PTY event", async () => {
  let attempts = 0;
  const { launcher, calls, scheduled } = harness({
    sourceTicket: async () => ({ ok: true, ticket: frontierTicket() }),
    releaseTerminal: async (sid) => {
      calls.releases.push(sid);
      attempts += 1;
      return attempts === 1
        ? { ok: false, released: false, error: "emitter unavailable" }
        : { ok: true, released: true };
    },
  });
  await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  const first = await launcher.onWorkerSessionEnded({
    id: "pane-2", kind: "exit", processExited: true, generation: 9, pid: 31337, exitCode: 0,
  });
  assert.equal(first.released, false);
  assert.equal(launcher.record("pane-2").state, "release_failed");
  assert.equal(launcher.record("pane-2").leaseId, "lease-1");
  assert.deepEqual(launcher.heldSessions(), ["pane-2#4242.1"]);
  assert.equal(scheduled.length, 1);
  await scheduled[0]();
  assert.equal(launcher.record("pane-2").state, "exited");
  assert.equal(launcher.record("pane-2").leaseId, null);
  assert.deepEqual(launcher.heldSessions(), []);
});

test("a KILL intent retains the worker lease until the matching PTY generation exits", async () => {
  const { launcher, calls } = harness({
    sourceTicket: async () => ({ ok: true, ticket: frontierTicket() }),
  });
  await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  const intent = await launcher.onWorkerSessionEnded({
    id: "pane-2", kind: "kill", processExited: false, generation: 9, pid: 31337,
  });
  assert.equal(intent.released, false);
  assert.equal(launcher.record("pane-2").state, "terminating");
  assert.equal(launcher.record("pane-2").leaseId, "lease-1");
  assert.deepEqual(launcher.heldSessions(), ["pane-2#4242.1"]);
  assert.equal(calls.releases.length, 0);

  const stale = await launcher.onWorkerSessionEnded({
    id: "pane-2", kind: "exit", processExited: true, generation: 8, pid: 30000, exitCode: 1,
  });
  assert.equal(stale.released, false);
  assert.equal(launcher.record("pane-2").state, "terminating");
  assert.equal(calls.releases.length, 0);

  const exited = await launcher.onWorkerSessionEnded({
    id: "pane-2", kind: "exit", processExited: true, generation: 9, pid: 31337, exitCode: 1,
  });
  assert.equal(exited.released, true);
  assert.equal(calls.releases.length, 1);
  const again = await launcher.onWorkerSessionEnded({
    id: "pane-2", kind: "exit", processExited: true, generation: 9, pid: 31337, exitCode: 1,
  });
  assert.equal(again.released, false);
  assert.equal(calls.releases.length, 1);
});

test("an end event for a pane this launcher never launched is a no-op", async () => {
  const { launcher, calls } = harness();
  const r = await launcher.onWorkerSessionEnded({ id: "pane-99", kind: "exit", exitCode: 1 });
  assert.equal(r.released, false);
  assert.equal(calls.releases.length, 0);
});

test("heldSessions() retains terminating generations for dead-holder reaping at shell exit", async () => {
  const { launcher } = harness();
  await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  await launcher.launchWorkerPane({ paneId: "pane-3", selection: SELECTION });
  assert.deepEqual(launcher.heldSessions().sort(), ["pane-2#4242.1", "pane-3#4242.2"]);
  await launcher.onWorkerSessionEnded({
    id: "pane-3", kind: "kill", processExited: false, generation: 9, pid: 31337,
  });
  assert.deepEqual(launcher.heldSessions().sort(), ["pane-2#4242.1", "pane-3#4242.2"]);
});

// ---- construction -------------------------------------------------------------------------------

test("a launcher without the shell's SUPERVISED spawn cannot be constructed (invariant 2)", () => {
  assert.throws(() => createWorkerPaneLauncher({}), /spawnSession/);
});

test("the pid and generation of the running session are recorded from the shell's own spawn", async () => {
  const { launcher } = harness({ spawnSession: () => ({ pid: 31337, generation: 42 }) });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.record.pid, 31337, "a RUNNING pane published pid:null while claiming otherwise");
  assert.equal(res.record.sessionGeneration, 42);
  assert.equal(res.record.supervised, true);
});

test("a stale process observation never becomes literal supervised evidence", async () => {
  const { launcher } = harness({
    processIdentity: () => ({ pid: 31337, generation: 8 }),
  });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.launched, true, "the already-live session is not killed by an observer mismatch");
  assert.equal(res.record.pid, 31337);
  assert.equal(res.record.sessionGeneration, 9);
  assert.equal(res.record.supervised, false, "stale generation is not observed supervision");
});

test("launchWorkerPane NEVER throws, even when an injected dependency does", async () => {
  // The caller (main.js) has no try/catch, so this is a promise, not an aspiration. A terminal may
  // already be counted when the fault happens, so the fault path must still release it.
  const { launcher, calls } = harness({
    scrubEnv: () => { throw new Error("scrub exploded"); },
  });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.launched, false);
  assert.equal(res.record.state, "failed");
  assert.match(res.reason, /unexpected launcher fault/);
  assert.deepEqual(calls.releases, ["pane-2#4242.1"]);
  assert.deepEqual(launcher.heldSessions(), []);
});

test("a fault BEFORE this attempt has a session key never touches the session already in the pane", async () => {
  // The outer catch used to read `get(paneId)` — whatever record the pane held. Two of the injected
  // calls (`isSupervised`, `hasLiveSession`) run before this attempt has minted a key of its own, so
  // a throw from either made the catch release the RUNNING session's durable terminal and overwrite
  // its `running` record: BLOCKING-1's harm (an I-X3 terminal wrongly released or unreleasable)
  // arriving by a second route (validator MINOR-5). Nothing was counted for this attempt yet, so
  // the honest fault path is to release nothing and forget nothing.
  // It has to be the SAME launcher — one that already holds a live session in that pane — or the
  // catch's `get(paneId)` returns an empty record and the mutation is invisible. (The first version
  // of this test used a second launcher and stayed green with the fix reverted, which is the same
  // "a fix whose test cannot see it" defect the reviews raised.) So the faulting dependency is
  // toggled between the two attempts.
  for (const dep of ["isSupervised", "hasLiveSession"]) {
    let faulting = false;
    const boom = () => { if (faulting) throw new Error(`${dep} exploded`); return dep === "isSupervised"; };
    const { launcher, calls } = harness({ [dep]: boom });
    await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });   // a LIVE session
    const live = launcher.record("pane-2");
    assert.equal(live.state, "running", `${dep}: setup did not produce a live session`);
    calls.releases.length = 0;

    faulting = true;
    const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
    assert.equal(res.launched, false);
    assert.match(res.reason, new RegExp(`unexpected launcher fault: Error: ${dep} exploded`));
    assert.deepEqual(calls.releases, [],
      `${dep}: a fault before this attempt took anything released the LIVE session's terminal`);
    assert.equal(launcher.record("pane-2").state, "running",
      `${dep}: a faulted attempt overwrote the live session's record — every release gate keys on it`);
    assert.deepEqual(launcher.heldSessions(), [live.sessionId],
      `${dep}: the live session's durable terminal is no longer reported as held`);
  }
});

test("every state change is observable (invariant 27)", async () => {
  const { launcher, calls } = harness();
  await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  const states = calls.changes.map((c) => c.state);
  // THREE observations, not two, since 18E: `launching`, `running`, and the node ATTESTATION —
  // which does not change the launch state and does change the record (`nodeAttested`), so it is
  // published like every other change rather than mutated behind the observer's back.
  assert.deepEqual(states, ["launching", "running", "running"]);
});

// ---- 18E: the pane's Sovereign node record ------------------------------------------------------

/** A ticket whose Python side DID write a node record — the only shape that gets attested. */
function registeredTicket() {
  return { ...localTicket(), node_registration: {
    registered: true, node_key: "worker-pane-2", incarnation: 1, schema_version: "node@1.1",
    node_id: "0d2f-uuid", log_path: "C:/repo/.sovereign_store/nodes/node_events.jsonl",
    reason: null } };
}

const registeredHarness = (opts = {}) => harness({
  sourceTicket: async () => ({ ok: true, ticket: registeredTicket() }), ...opts });

test("a live pane's node record is attested with the PYTHON-minted node id and the real pid", async () => {
  const { launcher, calls } = registeredHarness();
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.launched, true);
  assert.deepEqual(calls.attestations,
    [{ nodeKey: "worker-pane-2", sessionId: res.sessionId, pid: 31337 }],
    "the attestation must name the node the TICKET minted, the SESSION it belongs to and the pid "
    + "the SHELL observed — three facts no one side has on its own");
  assert.equal(res.record.nodeAttested, true);
});

test("a pane whose ticket wrote NO node record is never attested (the stale-record defect)", async () => {
  // The first cut attested every pane, including the local and OP-6 ones that have no record by
  // design — so a pane id whose earlier grok session left a record open could be attested with an
  // ollama process's pid, on an append-only log that can never be corrected.
  const shapes = [undefined, null,
    { registered: false, reason: "a LOCAL pane holds no subscription terminal" }];
  for (const registration of shapes) {
    const ticket = { ...localTicket(), node_registration: registration };
    const { launcher, calls } = harness({ sourceTicket: async () => ({ ok: true, ticket }) });
    const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
    assert.equal(res.launched, true, "the pane still launches — it simply has no record");
    assert.deepEqual(calls.attestations, [],
      "attesting a pane with no record of its own can only land on someone else's");
    assert.equal(res.record.nodeAttested, false);
    assert.equal(res.record.nodeAttestation.applicable, false);
  }
});

test("nothing is attested for a pane that never launched", async () => {
  const { launcher, calls } = registeredHarness({ isSupervised: () => false });
  await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.deepEqual(calls.attestations, []);
});

test("the record KEEPS what the ticket wrote and what the release closed (18E `.live.electron`)", async () => {
  // Both ends of the node record's life were MEASURED by their producers and thrown away by the
  // shell: the ticket's `node_registration` was read for a branch and dropped, and the release's
  // `node_record` never left the emitter source. Nothing could then say whether a pane's record was
  // closed or left open — and "the record is closed" is exactly what §17.2(1) asks the live
  // acceptance leg to evidence.
  const { launcher } = harness({
    sourceTicket: async () => ({ ok: true, ticket: registeredTicket() }),
    releaseTerminal: async () => ({ ok: true, released: true,
      nodeRecord: { closed: true, node_key: "worker-pane-2", incarnation: 1 } }),
  });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.record.nodeRegistration.registered, true);
  assert.equal(res.record.nodeRegistration.node_id, "0d2f-uuid",
    "the record id is how a receipt binds this pane to a row on the durable log without "
    + "recomputing an identity derivation");
  assert.equal(res.record.nodeClosure, null, "nothing is closed while the session is running");

  await launcher.onWorkerSessionEnded({
    id: "pane-2", kind: "exit", processExited: true, generation: 9, pid: 31337, exitCode: 0,
  });
  const after = launcher.record("pane-2");
  assert.equal(after.state, "exited");
  assert.equal(after.nodeClosure.closed, true);
  assert.equal(after.nodeClosure.node_key, "worker-pane-2");
});

test("a release that FAILED still records what happened to the node record", async () => {
  // The two stores fail independently: a locked lease ledger and an unclosed node record are
  // different leaks, and recording the node half only on the happy branch would hide the one that
  // matters more (a record reading SPAWNING forever on an append-only log).
  const { launcher } = harness({
    sourceTicket: async () => ({ ok: true, ticket: registeredTicket() }),
    releaseTerminal: async () => ({ ok: false, released: false, error: "ledger locked",
      nodeRecord: { closed: false, node_key: "worker-pane-2", reason: "node log locked" } }),
  });
  await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  await launcher.onWorkerSessionEnded({
    id: "pane-2", kind: "exit", processExited: true, generation: 9, pid: 31337, exitCode: 0,
  });
  const after = launcher.record("pane-2");
  assert.equal(after.state, "release_failed");
  assert.equal(after.nodeClosure.closed, false);
  assert.match(after.nodeClosure.reason, /node log locked/);
});

test("a FAILED attestation never breaks a live governed session", async () => {
  // The session is running, supervised and holding its terminal. A bookkeeping fault at this point
  // must be recorded, not acted on: killing it would trade a wrong LOG for a dead pane.
  for (const attestSpawn of [
    async () => ({ ok: false, attested: false, error: "emitter exited 1" }),
    async () => { throw new Error("emitter blew up"); },
  ]) {
    const { launcher } = registeredHarness({ attestSpawn });
    const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
    assert.equal(res.launched, true, "a failed attestation must not un-launch a live session");
    assert.equal(res.record.state, "running");
    assert.equal(res.record.nodeAttested, false);
    assert.ok(res.record.nodeAttestation.error, "the failure must be RECORDED, not swallowed");
    assert.deepEqual(launcher.heldSessions(), [res.sessionId],
      "the durable terminal is still held by a session that is still running");
  }
});
