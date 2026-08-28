"use strict";
/**
 * Phase 18C `.close` — the pure rules behind the OP-12 live-acceptance receipt.
 *
 * The in-Electron check needs a window, a supervisor and the host's own CLIs; what can be falsified
 * here is the part that decides what the receipt is ALLOWED to claim. Every rule below exists
 * because a green 18C receipt could otherwise be produced by the wrong world:
 *
 *   • 18C's acceptance (directive §17) is ONE live probe + ONE in-Electron live receipt per provider,
 *     and its entry condition — the operator's own edit to `config/live_operation.json` — is unmet on
 *     this host. So this receipt evidences the FAIL-CLOSED world instead. The single most dangerous
 *     failure is a receipt that reads like acceptance. `worldIsFailClosed` therefore refuses to let
 *     the check claim anything if the operator HAS opened the switch: at that point the live legs are
 *     owed and must be run, not summarised.
 *   • A refusal is only evidence if it came from the gate it names. `authorityRefusalIsFailClosed`
 *     reads the GATE ID and the ticket's own gate map, never prose — the lesson `_gate_id` was
 *     written for. It also requires the gates BEFORE the live one to have PASSED: a refusal at
 *     `host_enumeration` would prove the option was never the host's, and a refusal with
 *     `cli_present:false` would prove nothing about the switch.
 *   • The §17 acceptance line "lease returned to 0" must be measured on the durable ledger and
 *     PAINTED, because invariant 27's "visible" cannot mean "computed".
 *   • §17 "no credential material in any log" is a measurement here, not a promise: sentinel values
 *     are planted under the OP-12 credential NAMES and must appear nowhere the run wrote.
 */
const test = require("node:test");
const assert = require("node:assert/strict");

const {
  OP12_PROVIDERS, OP12_SUBSCRIPTION_REFS, OP12_CREDENTIAL_NAMES, REQUIRED_OWED_KEYS,
  worldIsFailClosed, authorityRefusalIsFailClosed, uxGuardRefused, leasesAreZero,
  statusBarPaintsZeroOfOne, noCredentialMaterial, owedLegsAreNamed,
} = require("../selfcheck/op12-acceptance-verdict");

// ---- fixtures -------------------------------------------------------------------------------

/** The operator's real switch on this host: OP-6, so neither OP-12 provider is live. */
function op6Authorization(overrides = {}) {
  return {
    authorized: true,
    providers: ["claude_code", "openai_codex_cli"],
    terminals_per_subscription: 2,
    register_row: "OP-6",
    reason: "live operation authorized for ['claude_code', 'openai_codex_cli'] "
      + "(register OP-6, 2 terminals/subscription)",
    ...overrides,
  };
}

/** The ticket `tools/live/emit_worker_launch.py` really emits for a greyed OP-12 option (measured
 *  on this host, 2026-08-01 — see docs/evidence/PHASE18C_EVIDENCE_REPORT.md). */
function refusalTicket(provider, overrides = {}) {
  return {
    authorized: false,
    refused: true,
    refused_by: "live_operation",
    node_state: "launch_refused",
    reason: `LiveAuthorizationError: live operation not authorized for provider '${provider}': `
      + "live operation authorized for ['claude_code', 'openai_codex_cli'] (register OP-6, "
      + "2 terminals/subscription) — fail closed (directive §10.1/§11/§17; authorizing row OP-6)",
    launch: null,
    lease: null,
    subscription_governed: false,
    governor_released: true,
    gates: {
      selection_offered: true,
      live_operation_authorized: false,
      operator_terms_confirmed: true,
      cli_present: true,
      local_runtime_present: null,
      residency_scheduled: null,
      ix3_counted: false,
    },
    ...overrides,
  };
}

function refusedLaunch(provider, overrides = {}) {
  return {
    launched: false, refused: true, refusedBy: "live_operation",
    reason: refusalTicket(provider).reason,
    ...overrides,
  };
}

function attempt(provider, overrides = {}) {
  return {
    provider,
    ticket: refusalTicket(provider),
    launch: refusedLaunch(provider),
    sessions_before: 3,
    sessions_after: 3,
    ...overrides,
  };
}

function leaseStatus(overrides = {}) {
  return {
    subscriptions: {
      claude_code_subscription: { in_use: 0, allowance: 2, holders: [] },
      grok_build_subscription: { in_use: 0, allowance: 1, holders: [] },
      google_antigravity_subscription: { in_use: 0, allowance: 1, holders: [] },
      ...(overrides.subscriptions || {}),
    },
  };
}

function owedBlock(overrides = {}) {
  const base = {};
  for (const key of REQUIRED_OWED_KEYS) base[key] = `owed — see U234 / directive §17 (${key})`;
  return { ...base, ...overrides };
}

// ---- worldIsFailClosed ----------------------------------------------------------------------

test("the OP-6 switch puts this host in the fail-closed world both OP-12 providers are denied in", () => {
  const world = worldIsFailClosed(op6Authorization());
  assert.equal(world.fail_closed, true);
  assert.deepEqual(world.op12_authorized, []);
  assert.equal(world.register_row, "OP-6");
});

test("a switch that names an OP-12 provider is NOT the fail-closed world — the live legs are owed, "
  + "and this receipt may not stand in for them", () => {
  const world = worldIsFailClosed(op6Authorization({
    providers: ["claude_code", "openai_codex_cli", "grok_build"], register_row: "OP-12",
  }));
  assert.equal(world.fail_closed, false);
  assert.deepEqual(world.op12_authorized, ["grok_build"]);
  assert.match(world.reason, /live acceptance legs/i);
});

test("both OP-12 providers authorized is still not the fail-closed world", () => {
  const world = worldIsFailClosed(op6Authorization({
    providers: ["claude_code", "grok_build", "google_antigravity"],
  }));
  assert.equal(world.fail_closed, false);
  assert.deepEqual(world.op12_authorized, ["grok_build", "google_antigravity"]);
});

test("an unreadable authorization is not read as fail-closed-by-absence — an unknown world is "
  + "refused, never assumed", () => {
  for (const bad of [null, undefined, {}, { providers: "claude_code" }, 7]) {
    const world = worldIsFailClosed(bad);
    assert.equal(world.fail_closed, false, `${JSON.stringify(bad)} was read as fail-closed`);
    assert.match(world.reason, /could not be read|no authorization/i);
  }
});

// ---- authorityRefusalIsFailClosed ------------------------------------------------------------

test("the measured refusal — the AUTHORITY refused at the live-operation gate with everything "
  + "before it passed, nothing spawned and nothing leased", () => {
  for (const provider of OP12_PROVIDERS) {
    const v = authorityRefusalIsFailClosed(attempt(provider));
    assert.equal(v.ok, true, `${provider}: ${v.reasons.join(" | ")}`);
    assert.deepEqual(v.reasons, []);
  }
});

test("a refusal by the HOST-ENUMERATION gate is refused as evidence: it proves the option was not "
  + "the host's own, and says nothing about the operator's switch", () => {
  const v = authorityRefusalIsFailClosed(attempt("grok_build", {
    ticket: refusalTicket("grok_build", {
      refused_by: "host_enumeration",
      gates: { ...refusalTicket("grok_build").gates, selection_offered: false },
    }),
    launch: refusedLaunch("grok_build", { refusedBy: "host_enumeration" }),
  }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /host_enumeration|selection_offered/.test(r)), v.reasons.join(" | "));
});

test("ONLY the gate-id rule may catch a refusal by an unrelated gate — asserted in isolation, "
  + "because the harness found `refused_by !== live_operation` deletable with the suite green", () => {
  // Everything else is exactly the fail-closed shape: both producers agree, every earlier gate
  // passed, nothing leased, nothing started. The one thing wrong is WHICH gate refused — the
  // I-X3 allowance gate would refuse identically on a host whose switch is wide open.
  const gate = "ix3_allowance";
  const reason = "SubscriptionLimitExceeded: grok_build already holds its 1 terminal";
  const v = authorityRefusalIsFailClosed(attempt("grok_build", {
    ticket: refusalTicket("grok_build", { refused_by: gate, reason }),
    launch: refusedLaunch("grok_build", { refusedBy: gate, reason }),
  }));
  assert.equal(v.ok, false);
  assert.equal(v.reasons.length, 1, `expected exactly the gate-id reason: ${v.reasons.join(" | ")}`);
  assert.match(v.reasons[0], /ix3_allowance/);
});

test("ONLY the selection_offered rule may catch an unverified option — same isolation, same "
  + "reason: the host-enumeration case above is also caught by the gate-id rule", () => {
  const v = authorityRefusalIsFailClosed(attempt("google_antigravity", {
    ticket: refusalTicket("google_antigravity", {
      gates: { ...refusalTicket("google_antigravity").gates, selection_offered: false },
    }),
  }));
  assert.equal(v.ok, false);
  assert.equal(v.reasons.length, 1, `expected exactly the selection_offered reason: ${v.reasons.join(" | ")}`);
  assert.match(v.reasons[0], /selection_offered/);
});

test("a refusal with cli_present false is refused as evidence: an absent CLI would refuse the same "
  + "way on an unauthorized host and on an authorized one", () => {
  const v = authorityRefusalIsFailClosed(attempt("google_antigravity", {
    ticket: refusalTicket("google_antigravity", {
      gates: { ...refusalTicket("google_antigravity").gates, cli_present: false },
    }),
  }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /cli_present/.test(r)), v.reasons.join(" | "));
});

test("a launch that reports refused while the ticket carries a lease is refused — a refusal that "
  + "leased a terminal is not fail-closed", () => {
  const v = authorityRefusalIsFailClosed(attempt("grok_build", {
    ticket: refusalTicket("grok_build", {
      lease: { lease_id: "lease-1" },
      gates: { ...refusalTicket("grok_build").gates, ix3_counted: true },
    }),
  }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /lease/.test(r)), v.reasons.join(" | "));
  assert.ok(v.reasons.some((r) => /ix3_counted/.test(r)), v.reasons.join(" | "));
});

test("a governor slot left behind by the refusal is refused (governor_released false)", () => {
  const v = authorityRefusalIsFailClosed(attempt("grok_build", {
    ticket: refusalTicket("grok_build", { governor_released: false }),
  }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /governor_released/.test(r)), v.reasons.join(" | "));
});

test("a session count that moved during the attempt is refused however the ticket reads — the one "
  + "thing a refusal may never do is start something", () => {
  const v = authorityRefusalIsFailClosed(attempt("grok_build", { sessions_after: 4 }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /session/.test(r)), v.reasons.join(" | "));
});

test("an AUTHORIZED ticket is never read as a fail-closed refusal", () => {
  const v = authorityRefusalIsFailClosed(attempt("grok_build", {
    ticket: refusalTicket("grok_build", { authorized: true, refused: false }),
    launch: { launched: true, refused: false, refusedBy: null, reason: null },
  }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /authorized|launched/.test(r)), v.reasons.join(" | "));
});

test("the refusal must name ITS OWN provider and none of the other's identifying words "
  + "(operator directive §14, checked in both directions)", () => {
  const crossed = authorityRefusalIsFailClosed(attempt("grok_build", {
    ticket: refusalTicket("grok_build", {
      reason: "LiveAuthorizationError: live operation not authorized for provider 'grok_build': "
        + "use the Gemini CLI instead",
    }),
    launch: refusedLaunch("grok_build", {
      reason: "LiveAuthorizationError: live operation not authorized for provider 'grok_build': "
        + "use the Gemini CLI instead",
    }),
  }));
  assert.equal(crossed.ok, false);
  assert.ok(crossed.reasons.some((r) => /other provider|gemini/i.test(r)), crossed.reasons.join(" | "));

  const nameless = authorityRefusalIsFailClosed(attempt("google_antigravity", {
    ticket: refusalTicket("google_antigravity", { reason: "LiveAuthorizationError: not authorized" }),
    launch: refusedLaunch("google_antigravity", { reason: "LiveAuthorizationError: not authorized" }),
  }));
  assert.equal(nameless.ok, false);
  assert.ok(nameless.reasons.some((r) => /does not name/.test(r)), nameless.reasons.join(" | "));
});

test("the §14 rule reads the refusal's PROSE, not the scope list it enumerates — otherwise the "
  + "world 18C is trying to reach would fail its own honesty leg", () => {
  // The moment the operator names ONE OP-12 provider in their switch, the OTHER provider's refusal
  // carries `grok_build`/`google_antigravity` inside `scoped providers [...]` as DATA.
  const reason = "LiveAuthorizationError: live operation not authorized for provider "
    + "'google_antigravity': live operation authorized for ['claude_code', 'grok_build'] "
    + "(register OP-12, 2 terminals/subscription) — fail closed";
  const v = authorityRefusalIsFailClosed(attempt("google_antigravity", {
    ticket: refusalTicket("google_antigravity", { reason }),
    launch: refusedLaunch("google_antigravity", { reason }),
  }));
  assert.equal(v.ok, true, v.reasons.join(" | "));
  // …and the same word OUTSIDE a bracketed list is still refused
  const crossed = authorityRefusalIsFailClosed(attempt("google_antigravity", {
    ticket: refusalTicket("google_antigravity", { reason: `${reason} — try grok instead` }),
    launch: refusedLaunch("google_antigravity", { reason: `${reason} — try grok instead` }),
  }));
  assert.equal(crossed.ok, false);
  assert.ok(crossed.reasons.some((r) => /other provider/.test(r)), crossed.reasons.join(" | "));
});

test("the CLICK refusal is checked for the other provider's words too — it is the text the "
  + "operator actually reads, which is what §14 is about", () => {
  const v = uxGuardRefused({
    recorded: false, launched: false,
    error: "option google_antigravity/gemini-3.6 is unavailable (use the Grok CLI instead) — "
      + "cannot spawn a greyed option",
  }, "google_antigravity");
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /other provider/.test(r)), v.reasons.join(" | "));
});

test("the launch result's gate id and the ticket's must AGREE — one producer contradicting the "
  + "other is not evidence", () => {
  const v = authorityRefusalIsFailClosed(attempt("grok_build", {
    launch: refusedLaunch("grok_build", { refusedBy: "operator_terms" }),
  }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /operator_terms|disagree/.test(r)), v.reasons.join(" | "));
});

// ---- uxGuardRefused ---------------------------------------------------------------------------

test("the operator's own click is refused before the authority is even asked, with the reason", () => {
  const v = uxGuardRefused({
    recorded: false, launched: false,
    error: "option grok_build/grok-4.5 is unavailable (live operation not authorized for "
      + "'grok_build': live operation authorized for ['claude_code', 'openai_codex_cli'] "
      + "(register OP-6, 2 terminals/subscription)) — cannot spawn a greyed option",
  }, "grok_build");
  assert.equal(v.ok, true);
});

test("a click that was RECORDED is not a refusal, and a refusal with no reason is not honest", () => {
  assert.equal(uxGuardRefused({ recorded: true, launched: false, error: null }, "grok_build").ok, false);
  assert.equal(uxGuardRefused({ recorded: false, launched: false, error: "" }, "grok_build").ok, false);
  assert.equal(uxGuardRefused({ recorded: false, launched: true, error: "x" }, "grok_build").ok, false);
});

test("the UX refusal must name the provider whose option was clicked", () => {
  const v = uxGuardRefused({
    recorded: false, launched: false, error: "option is unavailable — cannot spawn a greyed option",
  }, "grok_build");
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /does not name/.test(r)), v.reasons.join(" | "));
});

// ---- leasesAreZero ----------------------------------------------------------------------------

test("both OP-12 subscriptions read zero on the durable ledger — the §17 lease line, measured", () => {
  const v = leasesAreZero(leaseStatus());
  assert.equal(v.ok, true);
  assert.deepEqual(v.in_use, { grok_build_subscription: 0, google_antigravity_subscription: 0 });
});

test("a subscription with no ledger entry at all reads zero — an absent resource holds nothing", () => {
  const v = leasesAreZero({ subscriptions: { claude_code_subscription: { in_use: 1 } } });
  assert.equal(v.ok, true);
  assert.deepEqual(v.in_use, { grok_build_subscription: 0, google_antigravity_subscription: 0 });
});

test("one held OP-12 terminal fails the leg, and names WHICH subscription holds it", () => {
  const v = leasesAreZero(leaseStatus({
    subscriptions: { grok_build_subscription: { in_use: 1, allowance: 1, holders: [{ lease_id: "l" }] } },
  }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /grok_build_subscription/.test(r)), v.reasons.join(" | "));
});

test("an unreadable lease status is not zero — it is unknown, and unknown fails closed", () => {
  for (const bad of [null, undefined, {}, { subscriptions: null }]) {
    const v = leasesAreZero(bad);
    assert.equal(v.ok, false, `${JSON.stringify(bad)} was read as zero`);
  }
});

// ---- statusBarPaintsZeroOfOne -----------------------------------------------------------------

test("the bar paints each OP-12 provider at 0/1 — computed is not visible (invariant 27)", () => {
  const v = statusBarPaintsZeroOfOne(
    [{ provider: "grok_build", label: "0/1", allowance: 1 },
      { provider: "google_antigravity", label: "0/1", allowance: 1 },
      { provider: "claude_code", label: "0/2", allowance: 2 }],
    "supervision READY · claude 0/2 · codex 0/2 · grok 0/1 · agy 0/1",
  );
  assert.equal(v.ok, true);
});

test("a bar that advertises an allowance the governor refuses fails the leg (U255)", () => {
  const v = statusBarPaintsZeroOfOne(
    [{ provider: "grok_build", label: "0/2", allowance: 2 },
      { provider: "google_antigravity", label: "0/1", allowance: 1 }],
    "grok 0/2 · agy 0/1",
  );
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /grok_build/.test(r)), v.reasons.join(" | "));
});

test("a row that exists in the model but was never painted fails the leg — the operator reads "
  + "pixels, not models", () => {
  const v = statusBarPaintsZeroOfOne(
    [{ provider: "grok_build", label: "0/1", allowance: 1 },
      { provider: "google_antigravity", label: "0/1", allowance: 1 }],
    "supervision READY · claude 0/2 · codex 0/2",
  );
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /painted/.test(r)), v.reasons.join(" | "));
});

test("a missing OP-12 row fails the leg", () => {
  const v = statusBarPaintsZeroOfOne([{ provider: "grok_build", label: "0/1", allowance: 1 }],
    "grok 0/1 · agy 0/1");
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /google_antigravity/.test(r)), v.reasons.join(" | "));
});

// ---- noCredentialMaterial ---------------------------------------------------------------------

test("§17: no credential material in anything this run wrote — sentinels planted under the OP-12 "
  + "credential names appear nowhere", () => {
  const sentinels = OP12_CREDENTIAL_NAMES.map((n) => `sow-sentinel-${n}-1234`);
  const v = noCredentialMaterial({ "main-process.log": "picker: spawn REFUSED (fail-closed)" }, sentinels);
  assert.equal(v.ok, true);
  assert.equal(v.sentinels_checked, OP12_CREDENTIAL_NAMES.length);
});

test("a sentinel that reached the log fails the leg and names the sink, never the value", () => {
  const sentinels = ["sow-sentinel-XAI_API_KEY-1234"];
  const v = noCredentialMaterial(
    { "main-process.log": `child env: XAI_API_KEY=sow-sentinel-XAI_API_KEY-1234` }, sentinels);
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /main-process\.log/.test(r)), v.reasons.join(" | "));
  assert.ok(v.reasons.every((r) => !r.includes("sow-sentinel-XAI_API_KEY-1234")),
    "the failure text repeated the sentinel value — a leak report must not itself leak");
});

test("a leg with no sentinels to look for proves nothing and says so", () => {
  const v = noCredentialMaterial({ "main-process.log": "" }, []);
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /no sentinel/.test(r)), v.reasons.join(" | "));
});

test("an unread sink is a failure, not a pass — a log that could not be read has not been checked", () => {
  const v = noCredentialMaterial({ "main-process.log": null }, ["sow-sentinel-x"]);
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /could not be read/.test(r)), v.reasons.join(" | "));
});

// ---- owedLegsAreNamed -------------------------------------------------------------------------

test("every 18C live acceptance leg this run could not perform is named, with a reference", () => {
  const v = owedLegsAreNamed(owedBlock());
  assert.equal(v.ok, true);
});

test("a missing OWED key fails — silence about an unevidenced leg reads as coverage", () => {
  const block = owedBlock();
  delete block[REQUIRED_OWED_KEYS[0]];
  const v = owedLegsAreNamed(block);
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => r.includes(REQUIRED_OWED_KEYS[0])), v.reasons.join(" | "));
});

test("an OWED marker that cites nothing a reader can look up fails", () => {
  const v = owedLegsAreNamed(owedBlock({ [REQUIRED_OWED_KEYS[1]]: "not done yet" }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => r.includes(REQUIRED_OWED_KEYS[1])), v.reasons.join(" | "));
});

test("the OWED key set names BOTH halves of §17's per-CLI login condition and U238, whose owner "
  + "the register says is 18C", () => {
  for (const key of ["grok_auth_state", "antigravity_auth_state", "probe_acceptance_holes"]) {
    assert.ok(REQUIRED_OWED_KEYS.includes(key), `${key} is not a required OWED key`);
  }
  const block = owedBlock();
  delete block.probe_acceptance_holes;
  assert.equal(owedLegsAreNamed(block).ok, false);
});

test("the OP-12 constants are the ones the rest of the build uses, not a third spelling", () => {
  assert.deepEqual(OP12_PROVIDERS, ["grok_build", "google_antigravity"]);
  assert.deepEqual(OP12_SUBSCRIPTION_REFS, {
    grok_build: "grok_build_subscription",
    google_antigravity: "google_antigravity_subscription",
  });
  for (const name of ["XAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"]) {
    assert.ok(OP12_CREDENTIAL_NAMES.includes(name), `${name} is not in the OP-12 credential names`);
  }
});
