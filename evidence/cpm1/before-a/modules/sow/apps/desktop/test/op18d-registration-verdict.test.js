"use strict";
/**
 * Phase 18D `.close` — the receipt's rules, each with a way to go RED.
 *
 * The `.amendment` gate found that the 18C OWED block had no red-able test: the rules ran only at
 * in-Electron emit time, so replacing a claim with a stronger one left every suite green (U296).
 * These tests are the answer for 18D. Each starts from a report that PASSES and breaks exactly one
 * thing, so a rule that stopped checking its fact is a red test in the ordinary `npm test` run.
 */
const test = require("node:test");
const assert = require("node:assert");

const {
  OP12_PROVIDERS, SUCCESSOR_SCHEMA, REQUIRED_OWED_KEYS,
  registrationIsWired, liveWorldUnchanged, owedLegsAreNamed, owedClaimsAgreeWithMeasurements,
  noCredentialMaterial,
} = require("../selfcheck/op18d-registration-verdict");
const { OWED } = require("../selfcheck/op18d-registration-selfcheck");
const { leasesAreZero } = require("../selfcheck/op12-acceptance-verdict");

/** A registration report shaped exactly as tools/live/emit_provider_node_registration.py emits. */
function goodReport() {
  const registration = (provider) => ({
    provider,
    registered: true,
    error: null,
    node_record: { adapter: provider, adapter_schema_version: SUCCESSOR_SCHEMA,
      validated_against: SUCCESSOR_SCHEMA, schema: SUCCESSOR_SCHEMA },
    node_state_during: "SPAWNING",
    node_state_after: "TERMINATED",
    lease_in_use_during: 1,
    lease_in_use_after: 0,
    allowance: 1,
    teardown: { lease_released: true, node_exit_recorded: true },
    log: { chain_ok: true, rows: 3, kinds: ["spawn", "transition", "exit"], path_is_scratch: true,
      lock_released: true },
  });
  return {
    schema: "provider_node_registration@1.0",
    cli_executed: false,
    live_model_call: false,
    vocabulary: {
      admits: { grok_build: SUCCESSOR_SCHEMA, google_antigravity: SUCCESSOR_SCHEMA },
      unadmitted_example: { kimi_k3: null },
      frozen_member_example: { claude_code: "node@1.0" },
    },
    real_switch: { readable: true, providers: ["claude_code", "openai_codex_cli"],
      op12_authorized: [], register_row: "OP-6", fail_closed_for_op12: true,
      path: "D:/repo/config/live_operation.json", env_override: false,
      env_var: "SOVEREIGN_LIVE_OPERATION_CONFIG" },
    registrations: { grok_build: registration("grok_build"),
      google_antigravity: registration("google_antigravity") },
    refusals: { unadmitted_adapter: { refused: true }, unsupervised_session: { refused: true },
      not_spawned_by_supervisor: { refused: true }, concurrent_log_holder: { refused: true },
      refusals_are_auditable: true, lock_released: true },
    durable_store: { unchanged: true,
      after: { node_event_log: { path: "D:/repo/.sovereign_store/nodes/node_events.jsonl",
        exists: false, sha256: null } } },
    ok: true,
  };
}

function goodWorld(report) {
  return { report, sessionsBefore: 0, sessionsAfter: 0,
    leaseZero: leasesAreZero({ subscriptions: {} }),   // the SHARED authority, absent ⇒ 0
    realLedgerUnchanged: true };
}

test("a well-formed report passes both rules", () => {
  assert.strictEqual(registrationIsWired(goodReport()).ok, true);
  assert.strictEqual(liveWorldUnchanged(goodWorld(goodReport())).ok, true);
});

test("no report at all is a refusal, not a pass", () => {
  for (const bad of [null, undefined, "", 7]) {
    assert.strictEqual(registrationIsWired(bad).ok, false);
  }
});

test("a report from a different producer is refused", () => {
  const r = goodReport();
  r.schema = "provider_node_registration@2.0";
  assert.strictEqual(registrationIsWired(r).ok, false);
});

test("a report claiming a CLI ran, or a live call, is refused", () => {
  for (const key of ["cli_executed", "live_model_call"]) {
    const r = goodReport();
    r[key] = true;
    assert.strictEqual(registrationIsWired(r).ok, false, key);
  }
});

for (const provider of OP12_PROVIDERS) {
  test(`${provider}: a vocabulary that stopped admitting it is refused`, () => {
    const r = goodReport();
    r.vocabulary.admits[provider] = null;
    assert.strictEqual(registrationIsWired(r).ok, false);
  });

  test(`${provider}: a record admitted by the FROZEN schema is refused (it cannot be)`, () => {
    const r = goodReport();
    r.registrations[provider].node_record.adapter_schema_version = "node@1.0";
    assert.strictEqual(registrationIsWired(r).ok, false);
  });

  test(`${provider}: an unregistered or errored provider is refused`, () => {
    const missed = goodReport();
    missed.registrations[provider].registered = false;
    assert.strictEqual(registrationIsWired(missed).ok, false);
    const errored = goodReport();
    errored.registrations[provider].error = "boom";
    assert.strictEqual(registrationIsWired(errored).ok, false);
  });

  test(`${provider}: a record that did not validate against ${SUCCESSOR_SCHEMA} is refused`, () => {
    const r = goodReport();
    r.registrations[provider].node_record.validated_against = null;
    assert.strictEqual(registrationIsWired(r).ok, false);
  });

  test(`${provider}: a node left alive after the session is refused (D-LOOP-1)`, () => {
    const r = goodReport();
    r.registrations[provider].node_state_after = "SPAWNING";
    assert.strictEqual(registrationIsWired(r).ok, false);
  });

  test(`${provider}: a terminal left held is refused`, () => {
    const r = goodReport();
    r.registrations[provider].lease_in_use_after = 1;
    assert.strictEqual(registrationIsWired(r).ok, false);
  });

  test(`${provider}: a log whose chain does not verify is refused (invariant 12)`, () => {
    const r = goodReport();
    r.registrations[provider].log.chain_ok = false;
    assert.strictEqual(registrationIsWired(r).ok, false);
  });

  test(`${provider}: a log missing the exit rows is refused`, () => {
    const r = goodReport();
    r.registrations[provider].log.kinds = ["spawn"];
    assert.strictEqual(registrationIsWired(r).ok, false);
  });
}

test("a frozen member reported as node@1.1 is refused — the amendment widened, it did not replace", () => {
  const r = goodReport();
  r.vocabulary.frozen_member_example.claude_code = SUCCESSOR_SCHEMA;
  assert.strictEqual(registrationIsWired(r).ok, false);
});

for (const fence of ["unadmitted_adapter", "unsupervised_session", "not_spawned_by_supervisor",
  "concurrent_log_holder"]) {
  test(`a ${fence} fence that stopped refusing is refused`, () => {
    const r = goodReport();
    r.refusals[fence] = { refused: false };
    assert.strictEqual(registrationIsWired(r).ok, false);
  });
}

test("a refusal that left no auditable event is refused", () => {
  const r = goodReport();
  r.refusals.refusals_are_auditable = false;
  assert.strictEqual(registrationIsWired(r).ok, false);
});

test("a touched durable store is refused", () => {
  const r = goodReport();
  r.durable_store.unchanged = false;
  assert.strictEqual(registrationIsWired(r).ok, false);
});

test("a report with NO durable-store block is refused, not passed over", () => {
  const r = goodReport();
  delete r.durable_store;
  assert.strictEqual(registrationIsWired(r).ok, false);
});

for (const provider of OP12_PROVIDERS) {
  test(`${provider}: an I-X3 allowance other than 1 is refused`, () => {
    const r = goodReport();
    r.registrations[provider].allowance = 2;
    assert.strictEqual(registrationIsWired(r).ok, false);
  });

  test(`${provider}: a record written somewhere other than a scratch log is refused`, () => {
    const r = goodReport();
    r.registrations[provider].log.path_is_scratch = false;
    assert.strictEqual(registrationIsWired(r).ok, false);
  });

  test(`${provider}: a node log whose lock was not handed back is refused (D-LOOP-1)`, () => {
    const r = goodReport();
    r.registrations[provider].log.lock_released = false;
    assert.strictEqual(registrationIsWired(r).ok, false);
  });
}

// ---- the live world -----------------------------------------------------------------------

test("a switch read through the environment override is refused", () => {
  // `load_live_authorization()` honours SOVEREIGN_LIVE_OPERATION_CONFIG ahead of the repo default
  // and the producer inherits this process's environment — the validator demonstrated a receipt
  // reporting `register_row: OP-12` for a file in %TEMP%. This receipt's claim is about the
  // operator's own file and nothing may stand in for it.
  const r = goodReport();
  r.real_switch.env_override = true;
  const v = liveWorldUnchanged(goodWorld(r));
  assert.strictEqual(v.ok, false);
  assert.ok(v.reasons.join(" ").includes("SOVEREIGN_LIVE_OPERATION_CONFIG"));
});

test("a report that does not say WHICH file it read is refused", () => {
  const r = goodReport();
  delete r.real_switch.path;
  assert.strictEqual(liveWorldUnchanged(goodWorld(r)).ok, false);
});

test("an OPEN operator switch refuses this receipt rather than passing quietly", () => {
  const r = goodReport();
  r.real_switch.op12_authorized = OP12_PROVIDERS.slice();
  r.real_switch.fail_closed_for_op12 = false;
  const v = liveWorldUnchanged(goodWorld(r));
  assert.strictEqual(v.ok, false);
  // …and it says WHY, in the words a reader needs: the live legs became runnable.
  assert.ok(v.reasons.join(" ").includes("live legs are runnable"));
});

test("an unreadable switch is refused, never read as permission", () => {
  const r = goodReport();
  r.real_switch.readable = false;
  assert.strictEqual(liveWorldUnchanged(goodWorld(r)).ok, false);
});

test("a live session born during the run is refused", () => {
  const w = goodWorld(goodReport());
  w.sessionsAfter = 1;
  assert.strictEqual(liveWorldUnchanged(w).ok, false);
});

test("a missing session count is refused rather than treated as zero", () => {
  const w = goodWorld(goodReport());
  w.sessionsBefore = null;
  w.sessionsAfter = null;
  assert.strictEqual(liveWorldUnchanged(w).ok, false);
});

for (const provider of OP12_PROVIDERS) {
  test(`${provider}: a non-zero durable lease is refused`, () => {
    const w = goodWorld(goodReport());
    w.leaseZero = leasesAreZero({ subscriptions: { [`${provider}_subscription`]: { in_use: 1 } } });
    const v = liveWorldUnchanged(w);
    assert.strictEqual(v.ok, false);
    assert.ok(v.reasons.join(" ").includes(`${provider}_subscription`));
  });
}

test("an ABSENT lease bucket is read as 0 by the shared authority, not as a defect", () => {
  // The ledger only creates a bucket once something has been counted in it, so absent genuinely
  // holds nothing. This rule's first draft re-implemented the lease check instead of using
  // `leasesAreZero`, read absent as a failure, and the in-Electron run went red on a world that
  // was correct — one rule, one place, is the point.
  const w = goodWorld(goodReport());
  assert.deepStrictEqual(w.leaseZero.in_use,
    { grok_build_subscription: 0, google_antigravity_subscription: 0 });
  assert.strictEqual(liveWorldUnchanged(w).ok, true);
});

test("an UNREADABLE lease status is refused, never read as zero", () => {
  const w = goodWorld(goodReport());
  w.leaseZero = leasesAreZero(null);
  assert.strictEqual(liveWorldUnchanged(w).ok, false);
  w.leaseZero = undefined;
  assert.strictEqual(liveWorldUnchanged(w).ok, false);
});

test("a changed operator ledger file is refused", () => {
  const w = goodWorld(goodReport());
  w.realLedgerUnchanged = false;
  assert.strictEqual(liveWorldUnchanged(w).ok, false);
});

// ---- the OWED block -----------------------------------------------------------------------

test("the shipped OWED block names every required leg", () => {
  const v = owedLegsAreNamed(OWED);
  assert.deepStrictEqual(v.reasons, []);
  assert.strictEqual(v.ok, true);
  assert.deepStrictEqual(Object.keys(OWED).sort(), REQUIRED_OWED_KEYS.slice().sort());
});

test("dropping, emptying or padding an OWED key is refused", () => {
  for (const key of REQUIRED_OWED_KEYS) {
    const without = { ...OWED };
    delete without[key];
    assert.strictEqual(owedLegsAreNamed(without).ok, false, `missing ${key}`);
    assert.strictEqual(owedLegsAreNamed({ ...OWED, [key]: "owed" }).ok, false, `thin ${key}`);
  }
});

test("an EXTRA owed key is refused — the required set is the contract, both ways", () => {
  assert.strictEqual(owedLegsAreNamed({ ...OWED, something_else: "x".repeat(60) }).ok, false);
});

test("the OWED text still says a live probe has never run, and that no durable record exists", () => {
  assert.ok(/NEVER executed/.test(OWED.live_provider_probe));
  assert.ok(/SCRATCH log/.test(OWED.durable_node_record_for_a_live_session));
  assert.ok(/operator's own durable node log/.test(OWED.durable_node_record_for_a_live_session));
});

// ---- OWED claims vs MEASUREMENTS — the U296 remedy, completed --------------------------------
// Keyword-shaped rules were only half of it: the validator showed that a REWORDED false claim
// passed `owedLegsAreNamed` and that the report already measured the fact contradicting it, with
// no rule reading the measurement. These are that rule.

test("the shipped OWED claims agree with a report that measured them", () => {
  const v = owedClaimsAgreeWithMeasurements(OWED, goodReport());
  assert.deepStrictEqual(v.reasons, []);
  assert.strictEqual(v.ok, true);
});

test("a REWORDED durable-record claim is refused even though it is long and present", () => {
  const lie = { ...OWED,
    durable_node_record_for_a_live_session:
      "A Sovereign node record now exists on the operator's own durable node log for a live "
      + "session of each provider, so nothing is owed on this leg at all." };
  assert.strictEqual(owedLegsAreNamed(lie).ok, true);            // the shape rule cannot see it…
  assert.strictEqual(owedClaimsAgreeWithMeasurements(lie, goodReport()).ok, false);   // …this can
});

test("the claim is refused when the report MEASURED a durable node log that exists", () => {
  const r = goodReport();
  r.durable_store.after.node_event_log.exists = true;
  const v = owedClaimsAgreeWithMeasurements(OWED, r);
  assert.strictEqual(v.ok, false);
  assert.ok(v.reasons.join(" ").includes("PRESENT"));
});

test("the claim is refused when the report never measured the durable node log", () => {
  const r = goodReport();
  delete r.durable_store.after;
  assert.strictEqual(owedClaimsAgreeWithMeasurements(OWED, r).ok, false);
});

test("an OWED block calling the switch unopened is refused when the report says it is open", () => {
  const r = goodReport();
  r.real_switch.op12_authorized = OP12_PROVIDERS.slice();
  assert.strictEqual(owedClaimsAgreeWithMeasurements(OWED, r).ok, false);
});

// ---- the credential scan ------------------------------------------------------------------

test("a sentinel in any sink is reported by sink, never by value", () => {
  const v = noCredentialMaterial({ "a log": "before sow-18d-sentinel-XAI_API_KEY-1 after" },
    ["sow-18d-sentinel-XAI_API_KEY-1"]);
  assert.strictEqual(v.ok, false);
  assert.ok(v.reasons[0].includes("a log"));
  assert.ok(!v.reasons[0].includes("sow-18d-sentinel"));
});

test("a clean scan reports what it checked", () => {
  const v = noCredentialMaterial({ "a log": "nothing here", "another": null }, ["s1", "s2"]);
  assert.strictEqual(v.ok, true);
  assert.deepStrictEqual(v.sinks_checked, ["a log", "another"]);
  assert.strictEqual(v.sentinels_checked, 2);
});
