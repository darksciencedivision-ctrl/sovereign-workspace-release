"use strict";
/**
 * Verdict rules for the Phase 18D `.close` in-Electron receipt — separated from the check that
 * runs them so every rule is unit-testable in the ordinary suite (apps/desktop/test/
 * op18d-registration-verdict.test.js), which is the U296 lesson from the `.amendment` gate: a rule
 * that only runs at emit time is a rule that has never been observed to fail.
 *
 * The receipt makes two claims that must not be confusable:
 *
 *   1. **the registration wiring is real** — both OP-12 providers register as Sovereign nodes
 *      through the product path, under `node@1.1`, on a hash-chained append-only log, and the
 *      record is closed with the session;
 *   2. **the operator's live world is unchanged** — their switch still cites OP-6, both providers
 *      are still DENIED, no pane was opened, no terminal leased, no live call made.
 *
 * `registrationIsWired` gates the first. `liveWorldUnchanged` gates the second, and it is what
 * stops this receipt ever standing in for the live acceptance legs 18C skipped: if the operator
 * opens their switch, this receipt is no longer the right evidence and must be re-run as the live
 * one, so the rule REFUSES rather than passing quietly.
 */

const OP12_PROVIDERS = Object.freeze(["grok_build", "google_antigravity"]);
const SUCCESSOR_SCHEMA = "node@1.1";
const FROZEN_SCHEMA = "node@1.0";

/** Every leg of §17 acceptance this fail-closed world still cannot perform. */
const REQUIRED_OWED_KEYS = Object.freeze([
  "live_provider_probe",
  "live_in_electron_receipt",
  "durable_node_record_for_a_live_session",
  "antigravity_auth_state",
  "grok_auth_state",
  "operator_live_switch",
]);

function fail(reasons) { return { ok: reasons.length === 0, reasons }; }

/**
 * The registration report says the vocabulary admits both providers, both registered, and the
 * fence still refuses what no version admits.
 */
function registrationIsWired(report) {
  const r = [];
  if (!report || typeof report !== "object") return fail(["no registration report"]);
  if (report.schema !== "provider_node_registration@1.0") {
    r.push(`registration report schema is ${JSON.stringify(report.schema)}`);
  }
  if (report.cli_executed !== false) r.push("the report claims a CLI was executed");
  if (report.live_model_call !== false) r.push("the report claims a live model call");
  const vocab = report.vocabulary || {};
  for (const p of OP12_PROVIDERS) {
    if (!vocab.admits || vocab.admits[p] !== SUCCESSOR_SCHEMA) {
      r.push(`${p} is not admitted by ${SUCCESSOR_SCHEMA} (got ${JSON.stringify(vocab.admits && vocab.admits[p])})`);
    }
    const reg = (report.registrations || {})[p] || {};
    if (reg.registered !== true) r.push(`${p} did not register a node record`);
    if (reg.error) r.push(`${p} registration errored: ${reg.error}`);
    const rec = reg.node_record || {};
    if (rec.validated_against !== SUCCESSOR_SCHEMA) {
      r.push(`${p}'s record did not validate against ${SUCCESSOR_SCHEMA}`);
    }
    if (rec.adapter_schema_version !== SUCCESSOR_SCHEMA) {
      r.push(`${p}'s admitting version is ${JSON.stringify(rec.adapter_schema_version)}`);
    }
    // D-LOOP-1 in the node log: a one-shot session must not leave a node reading SPAWNING.
    if (reg.node_state_after !== "TERMINATED") {
      r.push(`${p}'s record was not closed (state ${JSON.stringify(reg.node_state_after)})`);
    }
    if (reg.lease_in_use_after !== 0) r.push(`${p} left ${reg.lease_in_use_after} terminal(s) held`);
    // I-X3 asserted, not merely displayed: the per-provider OP-12 allowance is 1 and is
    // code-pinned. A regression that merged or widened it must turn this receipt red.
    if (reg.allowance !== 1) r.push(`${p}'s I-X3 allowance reads ${JSON.stringify(reg.allowance)}, not 1`);
    const log = reg.log || {};
    if (log.chain_ok !== true) r.push(`${p}'s node log chain does not verify`);
    if (log.path_is_scratch !== true) r.push(`${p}'s record was NOT written to a scratch log`);
    if (log.lock_released !== true) r.push(`${p}'s node log lock was not handed back (D-LOOP-1)`);
    if (!Array.isArray(log.kinds) || log.kinds.join(",") !== "spawn,transition,exit") {
      r.push(`${p}'s node log reads ${JSON.stringify(log.kinds)}`);
    }
  }
  // The frozen file is still the provenance for a frozen member — the amendment widened the
  // vocabulary, it did not replace it.
  if (!vocab.frozen_member_example || vocab.frozen_member_example.claude_code !== FROZEN_SCHEMA) {
    r.push("claude_code is no longer reported as a node@1.0 member");
  }
  const ref = report.refusals || {};
  for (const key of ["unadmitted_adapter", "unsupervised_session", "not_spawned_by_supervisor",
    "concurrent_log_holder"]) {
    if (!ref[key] || ref[key].refused !== true) r.push(`the ${key} fence did not refuse`);
  }
  if (ref.refusals_are_auditable !== true) r.push("a refusal was not written to the append-only log");
  // UNCONDITIONAL. `report.durable_store && …` let a report WITHOUT the block satisfy the rule
  // silently, while `scope_note` states flatly that nothing was written to the operator's durable
  // node log — every other conjunct here is unconditional (spec-audit MINOR-7).
  if (!report.durable_store || report.durable_store.unchanged !== true) {
    r.push("the operator's durable store changed, or was not measured at all");
  }
  return fail(r);
}

/**
 * The OWED claims must agree with what the report MEASURED — not merely be present and wordy.
 *
 * `owedLegsAreNamed` checks shape; this checks truth. The validator's finding was exact: the
 * receipt could say "no record exists on the operator's own durable node log" while its own
 * `durable_store` block said one did, and every rule stayed green (U296's shape again, one level
 * up). A claim a measurement can contradict must be checked against that measurement.
 */
function owedClaimsAgreeWithMeasurements(owed, report) {
  const r = [];
  const store = (report && report.durable_store) || null;
  const after = (store && store.after && store.after.node_event_log) || null;
  const claimsNoDurableRecord = /No record exists on the operator's own durable node log/i
    .test(String((owed && owed.durable_node_record_for_a_live_session) || ""));
  if (!claimsNoDurableRecord) {
    r.push("OWED.durable_node_record_for_a_live_session no longer states that no record exists on "
      + "the operator's own durable node log — the claim this receipt rests on cannot be reworded "
      + "away, only made true or false");
  } else if (!after) {
    r.push("the report did not measure the operator's durable node log, so the OWED claim about "
      + "it is unverifiable");
  } else if (after.exists === true) {
    r.push(`OWED says no record exists on the operator's durable node log, but the report measured `
      + `${after.path} as PRESENT`);
  }
  // The live legs' OWED text and the world must agree too: a switch that is open makes
  // "the operator's switch denies both" false, and `liveWorldUnchanged` refuses on the same fact.
  const real = (report && report.real_switch) || {};
  if (Array.isArray(real.op12_authorized) && real.op12_authorized.length
      && /still cites OP-6|is the operator's own edit/i.test(String((owed && owed.operator_live_switch) || ""))) {
    r.push("OWED describes the live switch as unopened while the report says it names "
      + `${JSON.stringify(real.op12_authorized)}`);
  }
  return fail(r);
}

/**
 * The operator's world, unchanged and still fail-closed for both OP-12 providers.
 *
 * `sessionsBefore`/`sessionsAfter` and the lease counts are the negatives that make the first
 * claim mean something: the wiring was exercised WITHOUT opening a pane, leasing an operator
 * terminal, or spending anything.
 */
function liveWorldUnchanged({ report, sessionsBefore, sessionsAfter, leaseZero, realLedgerUnchanged }) {
  const r = [];
  const real = (report && report.real_switch) || {};
  if (real.readable !== true) r.push("the operator's live switch could not be read");
  // The claim is about the OPERATOR's file. `load_live_authorization()` honours
  // SOVEREIGN_LIVE_OPERATION_CONFIG ahead of the repo default and the producer inherits this
  // process's environment, so an env-pointed fixture could have supplied "the operator's switch"
  // and the receipt would have said so in good faith (gate-validator MEDIUM-3). Refused outright,
  // and the path is published so a reader can see WHICH file was read.
  if (real.env_override === true) {
    r.push(`the live switch was read through ${real.env_var || "an environment override"} `
      + `(${JSON.stringify(real.path)}) — this receipt's claim is about the operator's own file `
      + "and nothing may stand in for it");
  }
  if (typeof real.path !== "string" || !real.path) {
    r.push("the report did not disclose WHICH live-operation file it read");
  }
  if (!Array.isArray(real.op12_authorized) || real.op12_authorized.length !== 0) {
    // NOT a defect in the host's sense: it means the operator has opened the switch and the LIVE
    // acceptance legs are now runnable and owed. This receipt is then the wrong evidence.
    r.push(`the operator's switch now authorizes ${JSON.stringify(real.op12_authorized)} — `
      + "the live legs are runnable and this fail-closed receipt must not stand in for them "
      + "(directive §17)");
  }
  if (real.fail_closed_for_op12 !== true) r.push("the switch does not deny both OP-12 providers");
  if (!Number.isInteger(sessionsBefore) || sessionsAfter !== sessionsBefore) {
    r.push(`live session count moved ${sessionsBefore} → ${sessionsAfter}`);
  }
  // The §17 lease line, read through the SAME authority the 18C receipt uses
  // (`op12-acceptance-verdict.leasesAreZero`) rather than re-implemented here. It already carries
  // the two distinctions a second copy would get wrong: an ABSENT bucket genuinely holds nothing
  // (the ledger only creates one once something is counted in it), while an UNREADABLE status is
  // unknown and unknown fails closed. The first draft of this rule was a re-implementation, it
  // read an absent bucket as a defect, and the in-Electron run failed on a world that was correct.
  if (!leaseZero || leaseZero.ok !== true) {
    r.push(`the §17 lease line does not read zero: ${
      (leaseZero && Array.isArray(leaseZero.reasons) && leaseZero.reasons.join("; "))
      || "the durable lease status could not be read"}`);
  } else {
    for (const p of OP12_PROVIDERS) {
      const ref = `${p}_subscription`;
      const inUse = (leaseZero.in_use || {})[ref];
      if (inUse !== 0) r.push(`${ref} reads ${JSON.stringify(inUse)}, not 0`);
    }
  }
  if (realLedgerUnchanged !== true) r.push("the operator's durable lease ledger changed");
  return fail(r);
}

/** Every OWED key present and non-empty — the legs this run did not perform, each named. */
function owedLegsAreNamed(owed) {
  const r = [];
  for (const key of REQUIRED_OWED_KEYS) {
    const v = owed && owed[key];
    if (typeof v !== "string" || v.trim().length < 40) r.push(`OWED.${key} is missing or too thin`);
  }
  const extra = Object.keys(owed || {}).filter((k) => !REQUIRED_OWED_KEYS.includes(k));
  if (extra.length) r.push(`unexpected OWED keys: ${extra.join(", ")}`);
  return fail(r);
}

/** No sentinel value in any sink. Reported by SINK, never by value (§2.2). */
function noCredentialMaterial(sinks, sentinels) {
  const r = [];
  const checked = [];
  for (const [name, text] of Object.entries(sinks || {})) {
    checked.push(name);
    if (typeof text !== "string") continue;
    for (const s of sentinels || []) {
      if (s && text.includes(s)) r.push(`credential-shaped sentinel found in ${name}`);
    }
  }
  return { ...fail(r), sinks_checked: checked, sentinels_checked: (sentinels || []).length };
}

module.exports = {
  OP12_PROVIDERS, SUCCESSOR_SCHEMA, FROZEN_SCHEMA, REQUIRED_OWED_KEYS,
  registrationIsWired, liveWorldUnchanged, owedLegsAreNamed, owedClaimsAgreeWithMeasurements,
  noCredentialMaterial,
};
